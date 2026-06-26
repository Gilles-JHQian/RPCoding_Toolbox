"""Pipeline step definitions: the fixed-order DAG, step kinds, and per-step outputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rpcoding.core import paths


class StepKind(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    OPTIONAL = "optional"  # automated but skippable (external denoise)


class Step(StrEnum):
    CREATE_RESULTS = "create_results"
    CONCAT_WAVS = "concat_wavs"
    BUILD_TRIALINFO = "build_trialinfo"
    DENOISE = "denoise"
    MARK_FIRST_STIMS = "mark_first_stims"
    MAKE_EVENTS = "make_events"
    RUN_MFA = "run_mfa"
    RESPONSE_CODING = "response_coding"
    WRITE_TRIALS = "write_trials"


class EffectiveState(StrEnum):
    NOT_STARTED = "not_started"
    BLOCKED = "blocked"  # an upstream step isn't done yet
    NEEDS_MANUAL = "needs_manual"
    DONE = "done"
    STALE = "stale"  # done, but an upstream output changed since
    ERROR = "error"
    # Subject-level only (never a per-step state): a manual "this subject has a problem" flag the
    # user sets; it takes precedence over the computed status in the subject list.
    FLAGGED = "flagged"


@dataclass(frozen=True)
class StepSpec:
    step: Step
    title: str
    kind: StepKind
    deps: tuple[Step, ...]
    outputs: tuple[str, ...]  # paths relative to the results dir


_S = Step
STEP_SPECS: dict[Step, StepSpec] = {
    _S.CREATE_RESULTS: StepSpec(_S.CREATE_RESULTS, "Create results folder", StepKind.AUTO, (), ()),
    _S.CONCAT_WAVS: StepSpec(
        _S.CONCAT_WAVS,
        "Concatenate WAVs → allblocks.wav",
        StepKind.AUTO,
        (_S.CREATE_RESULTS,),
        (paths.ALLBLOCKS_WAV, paths.BLOCK_WAV_ONSETS_MAT),
    ),
    _S.BUILD_TRIALINFO: StepSpec(
        _S.BUILD_TRIALINFO,
        "Build trialInfo.mat",
        StepKind.AUTO,
        (_S.CREATE_RESULTS,),
        (paths.TRIALINFO_MAT,),
    ),
    _S.DENOISE: StepSpec(
        _S.DENOISE, "Denoise (optional)", StepKind.OPTIONAL, (_S.CONCAT_WAVS,), ()
    ),
    _S.MARK_FIRST_STIMS: StepSpec(
        _S.MARK_FIRST_STIMS,
        "Mark first stimuli → first_stims.txt",
        StepKind.MANUAL,
        (_S.CONCAT_WAVS,),
        (paths.FIRST_STIMS_TXT,),
    ),
    _S.MAKE_EVENTS: StepSpec(
        _S.MAKE_EVENTS,
        "Generate cue + condition events",
        StepKind.AUTO,
        (_S.BUILD_TRIALINFO, _S.MARK_FIRST_STIMS),
        (paths.CUE_EVENTS_TXT, paths.CONDITION_EVENTS_TXT),
    ),
    _S.RUN_MFA: StepSpec(
        _S.RUN_MFA,
        "MFA forced alignment",
        StepKind.AUTO,
        (_S.MAKE_EVENTS,),
        (f"{paths.MFA_DIRNAME}/mfa_stim_words.txt",),
    ),
    _S.RESPONSE_CODING: StepSpec(
        _S.RESPONSE_CODING,
        "Manual response coding",
        StepKind.MANUAL,
        (_S.RUN_MFA,),
        (paths.RESP_WORDS_ERRORS_TXT,),
    ),
    _S.WRITE_TRIALS: StepSpec(
        _S.WRITE_TRIALS,
        "Write response coding → Trials.mat",
        StepKind.AUTO,
        (_S.RESPONSE_CODING,),
        (),  # writes into D_Data/**/mat, not the results dir
    ),
}

STEP_ORDER: tuple[Step, ...] = tuple(STEP_SPECS)

# Short labels for the subject list's "current step" column (the per-step titles are too long).
STEP_SHORT: dict[Step, str] = {
    _S.CREATE_RESULTS: "Setup",
    _S.CONCAT_WAVS: "Concat",
    _S.BUILD_TRIALINFO: "trialInfo",
    _S.DENOISE: "Denoise",
    _S.MARK_FIRST_STIMS: "First stim",
    _S.MAKE_EVENTS: "Events",
    _S.RUN_MFA: "MFA",
    _S.RESPONSE_CODING: "Response",
    _S.WRITE_TRIALS: "Write Trials",
}
