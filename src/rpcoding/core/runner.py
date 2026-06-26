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
from rpcoding.core.mfa.runner import resolve_stim_dir, run_mfa
from rpcoding.core.paths import find_trials_mat
from rpcoding.core.progress import Reporter, StepProgress, noop
from rpcoding.core.rpcode.rpcode2trials import generate_trials
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind
from rpcoding.core.tasks import Task
from rpcoding.core.trialinfo.build import build_trialinfo
from rpcoding.core.wordlists import DEFAULT_NONWORD_LIST, DEFAULT_WORD_LIST, load_name_list

# Every action takes an optional progress Reporter; it defaults to None so callers that don't care
# (and the headless tests) can still invoke ``action(session)`` with a single argument.
StepAction = Callable[[SubjectSession, Reporter | None], None]


def _create_results(s: SubjectSession, report: Reporter | None = None) -> None:
    (report or noop)(0.0, "Creating results folder…")
    s.results_dir.mkdir(parents=True, exist_ok=True)
    (report or noop)(1.0, "Results folder ready")


def _concat_wavs(s: SubjectSession, report: Reporter | None = None) -> None:
    combine_wavs(
        s.all_blocks_dir,
        s.output_path(paths.ALLBLOCKS_WAV),
        s.output_path(paths.BLOCK_WAV_ONSETS_MAT),
        report=report,
    )


def _build_trialinfo(s: SubjectSession, report: Reporter | None = None) -> None:
    r = report or noop
    r(None, "Merging trialInfo blocks…")
    build_trialinfo(
        s.all_blocks_dir,
        s.output_path(paths.TRIALINFO_MAT),
        s.output_path("trialInfo.report.json"),
    )
    r(1.0, "Built trialInfo.mat")


def _denoise(s: SubjectSession, report: Reporter | None = None) -> None:
    """Optional external denoise: performed in Audacity on ``allblocks.wav``; running it here
    simply acknowledges that step as done (the pipeline keeps editing the same file in place)."""
    (report or noop)(1.0, "Denoise acknowledged")
    return None


def _make_events(s: SubjectSession, report: Reporter | None = None) -> None:
    r = report or noop
    r(0.05, "Locating Trials.mat…")
    trials_mat = find_trials_mat(s.d_data_subject_dir)
    r(0.25, "Generating cue events…")
    generate_cue_events(s.results_dir, trials_mat)
    r(0.65, "Generating condition events…")
    generate_condition_events(s.results_dir)
    r(1.0, "Wrote cue + condition events")


# The pipeline + the MFA aligner print these phase banners on stdout/stderr; map the ones we
# recognise to a coarse fraction so the bar advances through the long run. Order matters only for
# readability — each line bumps to the highest matching fraction. Unrecognised lines still surface
# live as the message (so even un-mapped MFA logging shows the run is alive). Checked most-specific
# first within a phase so e.g. "generating alignments" wins over a generic "generating".
_MFA_MARKS: tuple[tuple[str, float, str], ...] = (
    ("annotating stimuli", 0.12, "Annotating stimuli (loading from Box)…"),
    ("preparing patient", 0.28, "Preparing files for MFA…"),
    ("setting up corpus", 0.40, "Setting up the alignment corpus…"),
    ("generating base features", 0.48, "Generating acoustic features…"),
    ("generating mfcc", 0.48, "Generating acoustic features…"),
    ("calculating cmvn", 0.52, "Normalising features…"),
    ("mfa align", 0.45, "Running forced alignment…"),
    ("generating alignments", 0.62, "Generating alignments…"),
    ("collecting phone", 0.70, "Collecting aligned phones…"),
    ("exporting files", 0.82, "Exporting alignments…"),
    ("exporting", 0.82, "Exporting alignments…"),
    ("done! everything took", 0.88, "Alignment done; writing labels…"),
    ("finished processing", 1.0, "MFA complete"),
)


def _mfa_line_progress(line: str, state: dict) -> tuple[float | None, str]:
    """Map one MFA stdout line to (fraction, message). Keeps the highest fraction seen so the bar
    never goes backwards; non-banner lines surface verbatim (truncated) at the last fraction."""
    text = line.strip()
    if not text:
        return state["frac"], ""
    low = text.lower()
    for key, frac, msg in _MFA_MARKS:
        if key in low:
            state["frac"] = max(state["frac"], frac)
            return state["frac"], msg
    return state["frac"], text[:80]


def _mfa_failure(s: SubjectSession, log: str, log_path: Path) -> str | None:
    """Detect a *silent* MFA failure: the vendored pipeline catches per-patient errors and still
    exits 0, so a clean return code isn't proof of success. Returns an error message, or None if the
    run genuinely produced this subject's stimulus annotations."""
    lines = log.splitlines()
    tail = "\n".join(lines[-25:]).strip()
    detail = f"\n\n--- MFA output (last lines) ---\n{tail}" if tail else ""
    # The pipeline prints: "Errors occurred for the following patients: \n['D144', ...]".
    for i, line in enumerate(lines):
        if "Errors occurred for the following patients" in line:
            if s.subject in " ".join(lines[i : i + 3]):
                return (
                    f"MFA reported an error for {s.subject} (it still exited 0). "
                    f"Full log: {log_path}{detail}"
                )
    # Even without that banner, the real proof is a non-empty stimulus-annotation file.
    stim_words = s.results_dir / paths.MFA_DIRNAME / "mfa_stim_words.txt"
    try:
        wrote_output = stim_words.exists() and stim_words.stat().st_size > 0
    except OSError:
        wrote_output = False
    if not wrote_output:
        return (
            f"MFA produced no stimulus annotations ({paths.MFA_DIRNAME}/mfa_stim_words.txt is "
            f"empty) — usually the stim-annotation directory was not found. Full log: {log_path}"
            f"{detail}"
        )
    return None


def _run_mfa(s: SubjectSession, report: Reporter | None = None) -> None:
    r = report or noop
    task_config = s.config.mfa_task(s.task)
    if not task_config:
        raise ValueError(f"No MFA task config mapped for {s.task}; configure it in settings")
    patient_dir = s.results_dir.parent  # results root holding the subject folders
    home_dir = Path(s.config.droot).parent.parent  # the dir that contains 'Box'
    # Re-root the stim-annotation dir onto the real data root: the vendored task configs hardcode a
    # Windows 'Box\...' path that resolves nowhere off Windows, so MFA would silently align nothing.
    extra: list[str] = []
    stim_dir = resolve_stim_dir(s.config.droot, task_config)
    if stim_dir is not None:
        extra.append(f"task.stim_dir={stim_dir.as_posix()}")
    state = {"frac": 0.05}
    r(None, "Starting MFA…")

    def on_line(line: str) -> None:
        frac, msg = _mfa_line_progress(line, state)
        if msg:
            r(frac, msg)

    result = run_mfa(
        patient_dir, task_config, s.subject, home_dir=home_dir, extra=extra, on_line=on_line
    )
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
    failure = _mfa_failure(s, result.log, log_path)
    if failure:
        raise RuntimeError(failure)
    r(1.0, "MFA complete")


def _write_trials(s: SubjectSession, report: Reporter | None = None) -> None:
    # Mirror MATLAB, which `load`ed fixed word_lst/nonword_lst from the path: default to the bundled
    # lab lists when the user hasn't set their own (so the step works without manual configuration).
    r = report or noop
    r(0.05, "Loading word lists…")
    word_list = s.config.word_list or DEFAULT_WORD_LIST
    nonword_list = s.config.nonword_list or DEFAULT_NONWORD_LIST
    words = set(load_name_list(word_list, "words"))
    nonwords = set(load_name_list(nonword_list, "nonwords"))
    r(0.35, "Loading trialInfo…")
    trialinfo = load_trialinfo(s.output_path(paths.TRIALINFO_MAT))
    r(0.5, "Locating Trials.mat…")
    trials_mat = find_trials_mat(s.d_data_subject_dir)
    r(0.6, "Computing tags + writing Trials.mat…")
    generate_trials(s.results_dir, trials_mat, trialinfo, words, nonwords, task=s.task)
    r(1.0, "Wrote Trials.mat")


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
    *,
    report: Reporter | None = None,
) -> None:
    """Run one automated step, recording done/error in the manifest. Re-raises on failure.

    ``report`` (a :data:`~rpcoding.core.progress.Reporter`) receives within-step progress ticks.
    """
    if STEP_SPECS[step].kind == StepKind.MANUAL:
        raise ValueError(f"{step} is a manual step")
    action = actions.get(step)
    if action is None:
        raise NotImplementedError(f"No action registered for {step}")
    try:
        action(session, report)
    except Exception as exc:  # noqa: BLE001 - recorded then re-raised
        session.record_error(step, f"{type(exc).__name__}: {exc}")
        raise
    session.record_done(step)


def _runnable_steps(
    session: SubjectSession,
    actions: dict[Step, StepAction],
    *,
    force: bool,
    skip_optional: bool,
) -> list[Step]:
    """The steps :func:`run_pipeline` will execute in this pass (best-effort, for progress totals).

    Mirrors the loop below, but treats earlier planned steps as satisfying dependencies (so e.g.
    CONCAT counts even though CREATE_RESULTS hasn't run yet) and stops at the first blocked step.
    """
    planned: list[Step] = []
    done = {s for s in STEP_SPECS if session.effective_state(s) == EffectiveState.DONE}
    for step, spec in STEP_SPECS.items():
        if spec.kind == StepKind.MANUAL or step not in actions:
            continue
        if spec.kind == StepKind.OPTIONAL and skip_optional:
            continue
        if not all(d in done or d in planned for d in spec.deps):
            break  # blocked: the real loop stops here too
        if step in done and not force:
            continue
        planned.append(step)
    return planned


def run_pipeline(
    session: SubjectSession,
    actions: dict[Step, StepAction] = DEFAULT_ACTIONS,
    *,
    force: bool = False,
    skip_optional: bool = True,
    on_step: Callable[[StepProgress], None] | None = None,
) -> list[Step]:
    """Run runnable automated steps in order; stop when a manual/blocked step is reached.

    ``on_step`` receives a :class:`~rpcoding.core.progress.StepProgress` for every within-step tick,
    so a batch UI can show which step is running and how far it has got.
    """
    total = len(_runnable_steps(session, actions, force=force, skip_optional=skip_optional))
    ran: list[Step] = []
    index = 0
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
        index += 1
        report: Reporter | None = None
        if on_step is not None:
            title = STEP_SPECS[step].title

            def report(fraction, message, _step=step, _i=index, _title=title):
                on_step(StepProgress(_step, _i, total, fraction, message, _title))

            report(0.0, "Starting…")
        run_step(session, step, actions, report=report)
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
    on_step: Callable[[str, StepProgress], None] | None = None,
) -> dict[str, tuple]:
    """Run the automated pipeline for each subject; failures are collected, not fatal.

    ``on_progress(subject, result)`` fires when a subject finishes; ``on_step(subject, progress)``
    streams per-step progress while it runs.
    """
    results: dict[str, tuple] = {}
    for subj in subjects:
        session = SubjectSession(config, task, subj)
        sub_on_step = (lambda sp, _s=subj: on_step(_s, sp)) if on_step is not None else None
        try:
            results[subj] = ("ok", run_pipeline(session, actions, force=force, on_step=sub_on_step))
        except Exception as exc:  # noqa: BLE001 - batch keeps going
            results[subj] = ("error", f"{type(exc).__name__}: {exc}")
        if on_progress is not None:
            on_progress(subj, results[subj])
    return results
