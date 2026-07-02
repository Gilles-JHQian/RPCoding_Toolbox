r"""Fill MFA-dropped response rows with placeholders — one entry per spoken-response trial.

The MFA pipeline writes one response window per production trial (annotated_resp_windows.txt), then
aligns them. Where MFA fails to align a trial, textGrid2txt drops that empty-label row, so
mfa_resp_words comes up short and the write-Trials count check fails. Rather than drop those rows,
keep a placeholder for each un-aligned production trial:

- ``Omitted`` — the subject responded (per the ``Omission`` log for Lexical/UP, or by definition for
  Phoneme Sequencing where every trial is spoken), so a real response exists and a coder must
  review/code it (write-Trials refuses to run while any ``Omitted`` remains).
- ``NOISY`` — otherwise (no logged response): the lab's standard "no / unclear response" code, an
  acceptable final label.

"Production trials" are the ones the subject speaks on: ``Repeat`` for Lexical / Uniqueness Point,
**every** trial for Phoneme Sequencing (single "Listen" cue, 1:1). Each then has exactly one entry
in trial order, so the downstream positional mapping in ``rpcode2trials`` is also correct.
"""

from __future__ import annotations

import bisect
from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.labels import Interval, Tier, read_tier
from rpcoding.core.matio import load_trialinfo, trial_cue
from rpcoding.core.tasks import Task

OMITTED = "Omitted"
NOISY = "NOISY"


def _production_trials(task: Task, trialinfo: list[dict]) -> list[int]:
    """Indices (in trial order) of trials the subject speaks on, so a response should be coded."""
    if task == Task.PHONEME_SEQUENCING:
        return list(range(len(trialinfo)))  # every PS trial is a spoken repeat
    return [t for t in range(len(trialinfo)) if trial_cue(trialinfo[t]) == "Repeat"]


def fill_response_intervals(
    aligned: list[Interval | None],
    placeholders: list[tuple[float, float]],
    responded: list[bool],
) -> list[Interval]:
    """One interval per Repeat trial (in order): ``aligned[k]`` if MFA produced a response for that
    trial, else a placeholder at ``placeholders[k]`` labelled ``Omitted`` (the subject responded per
    the log) or ``NOISY`` (otherwise)."""
    out: list[Interval] = []
    for k, resp in enumerate(aligned):
        if resp is not None:
            out.append(resp)
        else:
            start, end = placeholders[k]
            out.append(Interval(start, end, OMITTED if responded[k] else NOISY))
    return out


def build_response_tier(results_dir: Path | str, *, task: Task) -> Tier | None:
    """Full one-per-production-trial response tier (with placeholders) from a subject's MFA output.

    Aligned responses are mapped to their production trial by time (which cue-event window they fall
    in), so a window capped short by ``max_dur`` never loses a real response. Returns ``None`` when
    the inputs are missing or don't line up, so callers can fall back to the raw MFA response.
    """
    results_dir = Path(results_dir)
    trialinfo_path = results_dir / paths.TRIALINFO_MAT
    cue_path = results_dir / paths.CUE_EVENTS_TXT
    if not (trialinfo_path.exists() and cue_path.exists()):
        return None
    trialinfo = load_trialinfo(trialinfo_path)
    cue_onsets = [iv.start for iv in read_tier(cue_path).intervals]
    if not cue_onsets or len(cue_onsets) != len(trialinfo):
        return None

    resp_path = results_dir / paths.MFA_DIRNAME / "mfa_resp_words.txt"
    mfa_resp = read_tier(resp_path).intervals if resp_path.exists() else []
    win_path = results_dir / paths.MFA_DIRNAME / "annotated_resp_windows.txt"
    windows = read_tier(win_path).intervals if win_path.exists() else []

    n = len(trialinfo)
    by_trial: dict[int, Interval] = {}
    for r in mfa_resp:
        if not r.label.strip():
            continue
        idx = min(max(bisect.bisect_right(cue_onsets, r.start) - 1, 0), n - 1)
        by_trial.setdefault(idx, r)  # first response wins (there is at most one per Repeat trial)

    production_idxs = _production_trials(task, trialinfo)
    if windows and len(windows) != len(production_idxs):
        windows = []  # can't line windows up 1:1 -> use cue-onset placeholder positions instead

    aligned = [by_trial.get(t) for t in production_idxs]
    if task == Task.PHONEME_SEQUENCING:
        responded = [True] * len(production_idxs)  # PS always elicits a spoken response
    else:
        responded = [
            str(trialinfo[t].get("Omission", "")).strip() == "Responded" for t in production_idxs
        ]
    placeholders = [
        (windows[k].start, windows[k].end) if windows else (cue_onsets[t], cue_onsets[t] + 1.0)
        for k, t in enumerate(production_idxs)
    ]
    return Tier("response", fill_response_intervals(aligned, placeholders, responded))


def count_omitted(intervals: list[Interval]) -> int:
    """Number of intervals still labelled ``Omitted`` (un-reviewed placeholders)."""
    return sum(1 for iv in intervals if iv.label.strip() == OMITTED)
