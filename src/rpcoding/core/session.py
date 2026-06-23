"""Per-subject session: resolved paths, manifest, and effective step states (incl. staleness)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.manifest import Manifest, StepRecord, fingerprint
from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind, StepSpec
from rpcoding.core.tasks import Task

_MANIFEST_NAME = "manifest.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class SubjectSession:
    config: AppConfig
    task: Task
    subject: str
    results_dir: Path = field(init=False)
    manifest: Manifest = field(init=False)

    def __post_init__(self) -> None:
        self.results_dir = paths.results_dir(self.config.droot, self.task, self.subject)
        mp = self.manifest_path
        self.manifest = (
            Manifest.load(mp)
            if mp.exists()
            else Manifest(task=str(self.task), subject=self.subject)
        )

    # ---- paths ----
    @property
    def manifest_path(self) -> Path:
        return self.results_dir / ".rpcoding" / _MANIFEST_NAME

    @property
    def d_data_subject_dir(self) -> Path:
        return paths.d_data_subject_dir(self.config.droot, self.task, self.subject)

    @property
    def all_blocks_dir(self) -> Path:
        return paths.cogan_task_data_dir(self.config.droot, self.subject, self.task)

    def output_path(self, rel: str) -> Path:
        return self.results_dir / rel

    def save(self) -> None:
        self.manifest.save(self.manifest_path)

    # ---- record outcomes ----
    def record_done(self, step: Step) -> None:
        spec = STEP_SPECS[step]
        rec = self.manifest.record(step)
        rec.state = "done"
        rec.error = None
        rec.ran_at = _now()
        rec.outputs = {o: fingerprint(self.output_path(o)) for o in spec.outputs}
        rec.dep_inputs = self._dep_fingerprints(step)
        self.save()

    def record_error(self, step: Step, message: str) -> None:
        rec = self.manifest.record(step)
        rec.state = "error"
        rec.error = message
        rec.ran_at = _now()
        self.save()

    # ---- state computation ----
    def _dep_fingerprints(self, step: Step) -> dict[str, str | None]:
        fps: dict[str, str | None] = {}
        for dep in STEP_SPECS[step].deps:
            for o in STEP_SPECS[dep].outputs:
                fps[o] = fingerprint(self.output_path(o))
        return fps

    def _outputs_present(self, spec: StepSpec) -> bool:
        return all(fingerprint(self.output_path(o)) is not None for o in spec.outputs)

    def effective_state(
        self, step: Step, _memo: dict[Step, EffectiveState] | None = None
    ) -> EffectiveState:
        if _memo is None:
            _memo = {}
        if step in _memo:
            return _memo[step]
        spec = STEP_SPECS[step]
        rec = self.manifest.steps.get(str(step), StepRecord())
        dep_states = [self.effective_state(d, _memo) for d in spec.deps]
        deps_done = all(s == EffectiveState.DONE for s in dep_states)

        if rec.state == "error":
            st = EffectiveState.ERROR
        elif rec.state == "done":
            stale = (
                not self._outputs_present(spec)
                or self._dep_fingerprints(step) != rec.dep_inputs
                or not deps_done
                or any(s == EffectiveState.STALE for s in dep_states)
            )
            st = EffectiveState.STALE if stale else EffectiveState.DONE
        elif not deps_done:
            st = EffectiveState.BLOCKED
        elif spec.kind == StepKind.MANUAL:
            st = EffectiveState.NEEDS_MANUAL
        else:
            st = EffectiveState.NOT_STARTED
        _memo[step] = st
        return st

    def effective_states(self) -> dict[Step, EffectiveState]:
        memo: dict[Step, EffectiveState] = {}
        return {s: self.effective_state(s, memo) for s in STEP_SPECS}
