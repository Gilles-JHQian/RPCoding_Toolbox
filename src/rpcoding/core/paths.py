"""Filesystem layout helpers for the Cogan Lab data tree.

All builders are pure and use ``pathlib`` only (no drive letters, OS-agnostic). ``droot`` is the
CoganLab data root (``$BOX/CoganLab``).
"""

from __future__ import annotations

from pathlib import Path

from rpcoding.core.tasks import COGAN_TASK_FOLDER, Task

# Canonical artifact filenames produced/consumed by the pipeline.
ALLBLOCKS_WAV = "allblocks.wav"
BLOCK_WAV_ONSETS_MAT = "block_wav_onsets.mat"
TRIALINFO_MAT = "trialInfo.mat"
FIRST_STIMS_TXT = "first_stims.txt"
CUE_EVENTS_TXT = "cue_events.txt"
CONDITION_EVENTS_TXT = "condition_events.txt"
RESP_WORDS_ERRORS_TXT = "bsliang_resp_words_errors.txt"
MFA_DIRNAME = "mfa"


def _task_value(task: Task | str) -> str:
    return task.value if isinstance(task, Task) else str(task)


def d_data_dir(droot: Path | str, task: Task | str) -> Path:
    """``$DROOT/D_Data/<task>`` — upstream per-task data (holds Trials.mat under ``**/mat/``)."""
    return Path(droot) / "D_Data" / _task_value(task)


def d_data_subject_dir(droot: Path | str, task: Task | str, subject: str) -> Path:
    return d_data_dir(droot, task) / subject


def cogan_task_folder(task: Task | str) -> str:
    """Human-readable Cogan_Task_Data subfolder name (e.g. 'Lexical No Delay')."""
    if isinstance(task, Task):
        return COGAN_TASK_FOLDER[task]
    return str(task)


def cogan_task_data_dir(droot: Path | str, subject: str, task: Task | str) -> Path:
    """Raw-acquisition dir holding per-block wavs + ``*_TrialData.mat`` ('All Blocks')."""
    return (
        Path(droot)
        / "ECoG_Task_Data"
        / "Cogan_Task_Data"
        / subject
        / cogan_task_folder(task)
        / "All Blocks"
    )


def results_root(droot: Path | str, task: Task | str) -> Path:
    """Per-task root of response-coding results."""
    return (
        Path(droot)
        / "ECoG_Task_Data"
        / "response_coding"
        / "response_coding_results"
        / _task_value(task)
    )


def results_dir(droot: Path | str, task: Task | str, subject: str) -> Path:
    """Per-subject results dir where the pipeline writes its artifacts."""
    return results_root(droot, task) / subject
