"""Run pipeline steps for a subject (automated steps) and batch across subjects.

Manual steps (first-stim marking, response coding) and steps not yet wired (MFA, write-Trials)
are skipped by the headless runner; the GUI drives those.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.audio.concat import combine_wavs
from rpcoding.core.config import AppConfig
from rpcoding.core.events.condition_events import generate_condition_events
from rpcoding.core.events.cue_events import generate_cue_events
from rpcoding.core.matio import load_trialinfo
from rpcoding.core.mfa.runner import run_mfa
from rpcoding.core.paths import find_trials_mat
from rpcoding.core.rpcode.rpcode2trials import generate_trials
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind
from rpcoding.core.tasks import Task
from rpcoding.core.trialinfo.build import build_trialinfo
from rpcoding.core.wordlists import load_name_list

StepAction = Callable[[SubjectSession], None]


def _create_results(s: SubjectSession) -> None:
    s.results_dir.mkdir(parents=True, exist_ok=True)


def _concat_wavs(s: SubjectSession) -> None:
    combine_wavs(
        s.all_blocks_dir,
        s.output_path(paths.ALLBLOCKS_WAV),
        s.output_path(paths.BLOCK_WAV_ONSETS_MAT),
    )


def _build_trialinfo(s: SubjectSession) -> None:
    build_trialinfo(
        s.all_blocks_dir,
        s.output_path(paths.TRIALINFO_MAT),
        s.output_path("trialInfo.report.json"),
    )


def _denoise(s: SubjectSession) -> None:
    """Optional external denoise: performed in Audacity on ``allblocks.wav``; running it here
    simply acknowledges that step as done (the pipeline keeps editing the same file in place)."""
    return None


def _make_events(s: SubjectSession) -> None:
    trials_mat = find_trials_mat(s.d_data_subject_dir)
    generate_cue_events(s.results_dir, trials_mat)
    generate_condition_events(s.results_dir)


def _run_mfa(s: SubjectSession) -> None:
    task_config = s.config.mfa_task(s.task)
    if not task_config:
        raise ValueError(f"No MFA task config mapped for {s.task}; configure it in settings")
    patient_dir = s.results_dir.parent  # results root holding the subject folders
    home_dir = Path(s.config.droot).parent.parent  # the dir that contains 'Box'
    result = run_mfa(patient_dir, task_config, s.subject, home_dir=home_dir)
    # Always keep the full pipeline output on disk so a failure can actually be diagnosed.
    log_path = s.results_dir / "mfa_run.log"
    try:
        s.results_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.log, encoding="utf-8")
    except OSError:
        pass
    if result.returncode != 0:
        tail = "\n".join(result.log.splitlines()[-25:]).strip()
        detail = f"\n\n--- MFA output (last lines) ---\n{tail}" if tail else ""
        raise RuntimeError(
            f"MFA exited with code {result.returncode}. Full log: {log_path}{detail}"
        )


def _write_trials(s: SubjectSession) -> None:
    if s.config.word_list is None or s.config.nonword_list is None:
        raise ValueError(
            "Word/nonword lists are not configured; set them in settings before writing Trials"
        )
    words = set(load_name_list(s.config.word_list, "words"))
    nonwords = set(load_name_list(s.config.nonword_list, "nonwords"))
    trialinfo = load_trialinfo(s.output_path(paths.TRIALINFO_MAT))
    trials_mat = find_trials_mat(s.d_data_subject_dir)
    generate_trials(s.results_dir, trials_mat, trialinfo, words, nonwords, task=s.task)


DEFAULT_ACTIONS: dict[Step, StepAction] = {
    Step.CREATE_RESULTS: _create_results,
    Step.CONCAT_WAVS: _concat_wavs,
    Step.BUILD_TRIALINFO: _build_trialinfo,
    Step.DENOISE: _denoise,
    Step.MAKE_EVENTS: _make_events,
    Step.RUN_MFA: _run_mfa,
    Step.WRITE_TRIALS: _write_trials,
}


def run_step(
    session: SubjectSession,
    step: Step,
    actions: dict[Step, StepAction] = DEFAULT_ACTIONS,
) -> None:
    """Run one automated step, recording done/error in the manifest. Re-raises on failure."""
    if STEP_SPECS[step].kind == StepKind.MANUAL:
        raise ValueError(f"{step} is a manual step")
    action = actions.get(step)
    if action is None:
        raise NotImplementedError(f"No action registered for {step}")
    try:
        action(session)
    except Exception as exc:  # noqa: BLE001 - recorded then re-raised
        session.record_error(step, f"{type(exc).__name__}: {exc}")
        raise
    session.record_done(step)


def run_pipeline(
    session: SubjectSession,
    actions: dict[Step, StepAction] = DEFAULT_ACTIONS,
    *,
    force: bool = False,
    skip_optional: bool = True,
) -> list[Step]:
    """Run runnable automated steps in order; stop when a manual/blocked step is reached."""
    ran: list[Step] = []
    for step, spec in STEP_SPECS.items():
        if spec.kind == StepKind.MANUAL:
            continue
        if spec.kind == StepKind.OPTIONAL and skip_optional:
            continue
        if step not in actions:
            continue  # not wired yet (e.g. MFA, write-Trials)
        state = session.effective_state(step)
        if state == EffectiveState.BLOCKED:
            break  # waiting on a manual/upstream step
        if state == EffectiveState.DONE and not force:
            continue
        run_step(session, step, actions)
        ran.append(step)
    return ran


def run_batch(
    config: AppConfig,
    task: Task,
    subjects: Iterable[str],
    actions: dict[Step, StepAction] = DEFAULT_ACTIONS,
    *,
    force: bool = False,
    on_progress: Callable[[str, tuple], None] | None = None,
) -> dict[str, tuple]:
    """Run the automated pipeline for each subject; failures are collected, not fatal."""
    results: dict[str, tuple] = {}
    for subj in subjects:
        session = SubjectSession(config, task, subj)
        try:
            results[subj] = ("ok", run_pipeline(session, actions, force=force))
        except Exception as exc:  # noqa: BLE001 - batch keeps going
            results[subj] = ("error", f"{type(exc).__name__}: {exc}")
        if on_progress is not None:
            on_progress(subj, results[subj])
    return results
