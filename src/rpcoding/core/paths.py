"""Filesystem layout helpers for the Cogan Lab data tree.

All builders are pure and use ``pathlib`` only (no drive letters, OS-agnostic). ``droot`` is the
CoganLab data root (``$BOX/CoganLab``).
"""

from __future__ import annotations

import re
from pathlib import Path

from rpcoding.core.tasks import COGAN_TASK_FOLDER, Task

_BLOCK_TRIALDATA_RE = re.compile(r"_Block_(\d+)_TrialData\.mat$", re.IGNORECASE)


def _norm(s: str) -> str:
    """Lower-case and strip spaces/underscores/hyphens, for tolerant folder-name matching."""
    return re.sub(r"[\s_\-]+", "", s.lower())


# How to recognise the right block folder despite inconsistent acquisition naming:
# narrow to the task-group folder under the subject, then disambiguate the session by keyword.
_TASK_GROUP = {
    Task.LEXICAL_NODELAY: "lexical",
    Task.LEXICAL_DELAY: "lexical",
    Task.UNIQUENESS_POINT: "uniqueness",
}
_TASK_KEYWORD = {Task.LEXICAL_NODELAY: "nodelay", Task.LEXICAL_DELAY: "delay"}
_TASK_ANTI_KEYWORD = {Task.LEXICAL_DELAY: "nodelay"}  # a Delay session must not be the NoDelay one

# Canonical artifact filenames produced/consumed by the pipeline.
ALLBLOCKS_WAV = "allblocks.wav"
# MFA denoises allblocks.wav in place and preserves the pre-denoise audio under this name.
ALLBLOCKS_ORIGINAL_WAV = "allblocks_original.wav"
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


def cogan_subject_dir(droot: Path | str, subject: str) -> Path:
    """``…/ECoG_Task_Data/Cogan_Task_Data/<subj>`` — holds one folder per task group."""
    return Path(droot) / "ECoG_Task_Data" / "Cogan_Task_Data" / subject


def cogan_task_folder_dir(droot: Path | str, subject: str, task: Task | str) -> Path:
    """The conventional per-subject task folder ('Lexical No Delay'). Acquisition wasn't consistent;
    see :func:`resolve_blocks_dir` for the tolerant run-time lookup."""
    return cogan_subject_dir(droot, subject) / cogan_task_folder(task)


def cogan_task_data_dir(droot: Path | str, subject: str, task: Task | str) -> Path:
    """Conventional raw-acquisition dir ('…/<task folder>/All Blocks')."""
    return cogan_task_folder_dir(droot, subject, task) / "All Blocks"


def _block_dirs_under(root: Path, max_depth: int = 4) -> dict[Path, set[int]]:
    """Dirs under ``root`` holding non-practice block TrialData mats -> their block numbers.

    A bounded-depth walk (not ``**``) so a huge per-trial-wav session folder is listed once rather
    than dragging an unbounded recursion through it.
    """
    out: dict[Path, set[int]] = {}
    frontier: list[tuple[Path, int]] = [(root, 0)]
    while frontier:
        d, depth = frontier.pop()
        try:
            for entry in d.iterdir():
                if entry.is_dir():
                    if depth < max_depth:
                        frontier.append((entry, depth + 1))
                elif "pract" not in entry.name.lower():
                    m = _BLOCK_TRIALDATA_RE.search(entry.name)
                    if m:
                        out.setdefault(d, set()).add(int(m.group(1)))
        except OSError:
            continue
    return out


def resolve_blocks_dir(subject_dir: Path | str, task: Task | str) -> Path:
    """Find the directory actually holding this task's per-block wavs / TrialData mats.

    Clean subjects keep them in ``<subj>/Lexical No Delay/All Blocks``, but acquisition was wildly
    inconsistent: the task folder may be named ``Lexical``, the block folder a timestamped session
    (e.g. ``…_NoDelay_201810281549``) possibly nested a level deep, and the same folder can mix
    practice and real sessions. Strategy: narrow to the matching task-group folder(s), collect the
    dirs holding non-practice block TrialData mats, and pick the one whose path best matches the
    task (NoDelay vs Delay) then has the most blocks. Falls back to the conventional path.
    """
    subject_dir = Path(subject_dir)
    task = Task.from_str(task) if not isinstance(task, Task) else task

    group = _TASK_GROUP.get(task, "")
    try:
        groups = [
            d for d in subject_dir.iterdir() if d.is_dir() and _norm(d.name).startswith(group)
        ]
    except OSError:
        groups = []
    candidates: dict[Path, set[int]] = {}
    for root in groups or [subject_dir]:
        candidates.update(_block_dirs_under(root))
    if not candidates:
        return subject_dir / cogan_task_folder(task) / "All Blocks"

    keyword = _TASK_KEYWORD.get(task)
    anti = _TASK_ANTI_KEYWORD.get(task)

    def score(d: Path) -> int:
        norm = _norm(str(d))
        s = len(candidates[d])
        if keyword and keyword in norm:
            s += 1000
        if anti and anti in norm:
            s -= 1000
        return s

    return max(candidates, key=score)


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


def find_trials_mat(d_data_subject_dir: Path | str) -> Path:
    """Locate the upstream ``**/mat/Trials.mat`` under a D_Data subject dir.

    Mirrors the MATLAB ``dir(.../**/mat/Trials.mat)`` lookup: raises if zero or more than one
    match (the pipeline requires exactly one).
    """
    matches = sorted(Path(d_data_subject_dir).glob("**/mat/Trials.mat"))
    if not matches:
        raise FileNotFoundError(f"No Trials.mat under {d_data_subject_dir} (**/mat/Trials.mat)")
    if len(matches) > 1:
        raise ValueError(f"Found more than one Trials.mat under {d_data_subject_dir}: {matches}")
    return matches[0]
