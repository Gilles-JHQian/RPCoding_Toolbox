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


def _exists(p: Path) -> bool:
    """``p.exists()`` that treats an un-stat-able cloud placeholder (OSError) as absent."""
    try:
        return p.exists()
    except OSError:
        return False


def _is_dir(p: Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


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

    def _completed_on_disk(self, step: Step) -> bool | None:
        """Whether a step's output exists on disk, or ``None`` if it leaves no detectable artifact.

        This lets the dashboard mark steps green for subjects already processed by the legacy
        pipeline (no manifest). ``None`` (denoise, write-Trials) falls back to the manifest record.
        """
        rd = self.results_dir
        if step == Step.CREATE_RESULTS:
            return _is_dir(rd)
        if step == Step.CONCAT_WAVS:
            return _exists(rd / paths.ALLBLOCKS_WAV)
        if step == Step.BUILD_TRIALINFO:
            return _exists(rd / paths.TRIALINFO_MAT)
        if step == Step.MARK_FIRST_STIMS:
            return _exists(rd / paths.FIRST_STIMS_TXT)
        if step == Step.MAKE_EVENTS:
            return _exists(rd / paths.CUE_EVENTS_TXT) and _exists(rd / paths.CONDITION_EVENTS_TXT)
        if step == Step.RUN_MFA:
            mfa = rd / paths.MFA_DIRNAME
            return _is_dir(mfa) and _exists(mfa / "mfa_stim_words.txt")
        if step == Step.RESPONSE_CODING:
            return _exists(rd / paths.RESP_WORDS_ERRORS_TXT) or _exists(rd / "response_coding.txt")
        return None  # DENOISE, WRITE_TRIALS: no reliable on-disk signal

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
        any_dep_stale = any(s == EffectiveState.STALE for s in dep_states)

        present = self._completed_on_disk(step)
        done = (rec.state == "done") if present is None else present

        # The output existing on disk wins over a leftover error record (file-existence = done),
        # so a step is never shown as Error once its artifact is present.
        if done:
            if rec.state == "done":
                # provenance available: a content-edit upstream marks this stale
                stale = (
                    self._dep_fingerprints(step) != rec.dep_inputs or not deps_done or any_dep_stale
                )
            else:
                # outputs exist but we never ran it (pre-existing): only structural staleness
                stale = not deps_done or any_dep_stale
            st = EffectiveState.STALE if stale else EffectiveState.DONE
        elif rec.state == "error":
            st = EffectiveState.ERROR
        elif present is not None and rec.state == "done":
            st = EffectiveState.STALE  # recorded done but the output is now gone
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

    def summary(self) -> tuple[int, int, EffectiveState]:
        """``(done, total, representative_state)`` for the subject-list row."""
        states = list(self.effective_states().values())
        total = len(states)
        done = sum(1 for s in states if s == EffectiveState.DONE)
        if EffectiveState.ERROR in states:
            rep = EffectiveState.ERROR
        elif done == total:
            rep = EffectiveState.DONE
        elif EffectiveState.STALE in states:
            rep = EffectiveState.STALE
        else:
            rep = EffectiveState.NOT_STARTED
        return done, total, rep

    def step_error(self, step: Step) -> str | None:
        """The recorded error message for a step (for the dashboard chip tooltip), if any."""
        return self.manifest.steps.get(str(step), StepRecord()).error
