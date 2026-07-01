"""Per-subject session: resolved paths, manifest, and effective step states (incl. staleness)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.manifest import Manifest, StepRecord, fingerprint
from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind, StepSpec
from rpcoding.core.tasks import Task

_MANIFEST_NAME = "manifest.json"


def _now() -> str:
    # Local time, tz-aware (e.g. ...T17:27:20-04:00) so manifest timestamps match the system clock.
    return datetime.now().astimezone().isoformat()


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


def _nonempty(p: Path) -> bool:
    """A real (non-placeholder) file with content; an empty file is treated as absent."""
    try:
        return p.stat().st_size > 0
    except OSError:
        return False


@dataclass
class SubjectSession:
    config: AppConfig
    task: Task
    subject: str
    results_dir: Path = field(init=False)
    manifest: Manifest = field(init=False)
    _blocks_dir: Path | None = field(init=False, default=None)
    _blocks_dirs: list[Path] | None = field(init=False, default=None)

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
        """The single best per-block wav/mat dir — resolved (name/subfolder-tolerant), memoized."""
        if self._blocks_dir is None:
            subject_dir = paths.cogan_subject_dir(self.config.droot, self.subject)
            self._blocks_dir = paths.resolve_blocks_dir(subject_dir, self.task)
        return self._blocks_dir

    @property
    def all_blocks_dirs(self) -> list[Path]:
        """All per-block session dirs (multi-session aware). One for most subjects; two when a task
        was recorded across separate session folders. Feed these to trialInfo build / wav concat."""
        if self._blocks_dirs is None:
            subject_dir = paths.cogan_subject_dir(self.config.droot, self.subject)
            self._blocks_dirs = paths.resolve_block_dirs(subject_dir, self.task)
        return self._blocks_dirs

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
                if o == paths.ALLBLOCKS_WAV:
                    # MFA denoises allblocks.wav in place, which would otherwise falsely stale every
                    # downstream step. Its sibling block_wav_onsets.mat (same concat step, untouched
                    # by MFA) still flags a genuine re-concat.
                    continue
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
            # An empty mfa_stim_words.txt is a failed/aborted run (the pipeline can leave a 0-byte
            # file behind), so require real content rather than mere existence.
            mfa = rd / paths.MFA_DIRNAME
            return _is_dir(mfa) and _nonempty(mfa / "mfa_stim_words.txt")
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

        # A recorded error from our most recent run is authoritative: show ERROR even if a
        # pre-existing or stale output artifact is still on disk (e.g. step 6 re-run that fails on
        # Trials.mat lookup while last run's cue_events.txt lingers; or write-Trials, whose output
        # doubles as its input and so always "exists"). Legacy subjects processed outside the app
        # have no manifest record, so the file-existence heuristic below still marks them done.
        if rec.state == "error":
            st = EffectiveState.ERROR
        else:
            done = (rec.state == "done") if present is None else present
            if done:
                if rec.state == "done":
                    # provenance available: an upstream content-edit marks this stale. Drop
                    # allblocks.wav from the recorded side too, so pre-exclusion manifests match.
                    recorded = {k: v for k, v in rec.dep_inputs.items() if k != paths.ALLBLOCKS_WAV}
                    stale = (
                        self._dep_fingerprints(step) != recorded or not deps_done or any_dep_stale
                    )
                else:
                    # outputs exist but we never ran it (pre-existing): only structural staleness
                    stale = not deps_done or any_dep_stale
                st = EffectiveState.STALE if stale else EffectiveState.DONE
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

    def status(self) -> tuple[int, int, EffectiveState, Step | None]:
        """One-pass subject status: ``(done, total, representative_state, current_step)``.

        Optional steps (Denoise) are excluded from the counts and the frontier: ``current_step`` is
        the first **required** step that isn't done (where the subject is "at"; ``None`` when all
        required steps are done). A manual ``flagged`` mark wins over the computed status; otherwise
        error > done > stale > not-started, over the required steps only.
        """
        states = self.effective_states()
        required = [
            (step, s) for step, s in states.items() if STEP_SPECS[step].kind != StepKind.OPTIONAL
        ]
        total = len(required)
        done = sum(1 for _step, s in required if s == EffectiveState.DONE)
        current = next((step for step, s in required if s != EffectiveState.DONE), None)
        if self.manifest.flagged:
            rep = EffectiveState.FLAGGED
        elif any(s == EffectiveState.ERROR for _step, s in required):
            rep = EffectiveState.ERROR
        elif done == total:
            rep = EffectiveState.DONE
        elif any(s == EffectiveState.STALE for _step, s in required):
            rep = EffectiveState.STALE
        else:
            rep = EffectiveState.NOT_STARTED
        return done, total, rep, current

    def summary(self) -> tuple[int, int, EffectiveState]:
        """``(done, total, representative_state)`` for the subject-list row (see :meth:`status`)."""
        done, total, rep, _current = self.status()
        return done, total, rep

    # ---- manual per-subject metadata (notes + problem flag) ----
    @property
    def notes(self) -> str:
        return self.manifest.notes

    def set_notes(self, text: str) -> None:
        """Persist free-text notes for this subject (creates the manifest if needed)."""
        if text == self.manifest.notes:
            return
        self.manifest.notes = text
        self.save()

    @property
    def flagged(self) -> bool:
        return self.manifest.flagged

    def set_flagged(self, value: bool) -> None:
        """Set/clear the manual 'has a problem' flag for this subject."""
        if bool(value) == self.manifest.flagged:
            return
        self.manifest.flagged = bool(value)
        self.save()

    # ---- automatic run advisories (e.g. multi-session auto-combine) ----
    @property
    def warnings(self) -> dict[str, str]:
        """Automatic advisories set by the last run, keyed by category (see :class:`Manifest`)."""
        return dict(self.manifest.warnings)

    def set_warning(self, key: str, message: str) -> None:
        """Record (and persist) an automatic advisory for ``key``; no-op if unchanged."""
        if self.manifest.warnings.get(key) == message:
            return
        self.manifest.warnings[key] = message
        self.save()

    def clear_warning(self, key: str) -> None:
        """Drop the advisory for ``key`` (e.g. a subject that is no longer multi-session)."""
        if key in self.manifest.warnings:
            del self.manifest.warnings[key]
            self.save()

    def step_error(self, step: Step) -> str | None:
        """The recorded error message for a step (for the dashboard chip tooltip), if any."""
        return self.manifest.steps.get(str(step), StepRecord()).error
