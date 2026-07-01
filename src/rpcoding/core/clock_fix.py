r"""Correct the EDF-vs-allblocks.wav clock drift from manual anchors (see memory clock-drift-fix).

cue_events / condition_events place each trial by the EDF trigger clock, which drifts from the
audio-recording clock, so the stimulus annotation slips later through each block and resets at the
boundary. Given a few **true** stimulus positions per block (``clock_anchors.txt``: label = trial
number, start = true audio onset), this re-maps each block's EDF-elapsed onto the true audio
timeline (piecewise-linear through the anchors, so it handles a non-linear block) and rewrites both.

The EDF trigger grid is itself accurate (``trigTimes_audioAligned - trigTimes`` is a constant
latency), so only the EDF-vs-audio rate needs fixing, which the anchors pin down.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rpcoding.core import paths
from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.matio import load_trialinfo, load_trials, trial_block

EDF_RATE = 3.0e4  # Trials.Auditory ticks per second
CUE_DURATION = 1.0  # seconds (matches make_cue_events_lr.m)
BACKUP_SUFFIX = ".before_clock_fix.txt"


def _anchor_trial(label: str) -> int | None:
    head = label.split("_", 1)[0].split()[0] if label else ""
    return int(head) if head.isdigit() else None


def load_anchors(path: Path | str) -> dict[int, float]:
    """``clock_anchors.txt`` -> ``{trial_number: true_audio_onset_s}`` (a later mark wins)."""
    anchors: dict[int, float] = {}
    for iv in read_tier(path, "clock_anchors").intervals:
        trial = _anchor_trial(iv.label)
        if trial is not None:
            anchors[trial] = iv.start
    return anchors


def _block_trials(trialinfo: list[dict]) -> list[list[int]]:
    """1-based trial numbers grouped per block, in order."""
    blocks: list[list[int]] = []
    cur: list[int] = []
    prev: float | None = None
    for t, ti in enumerate(trialinfo, start=1):
        b = float(trial_block(ti))
        if prev is not None and b != prev:
            blocks.append(cur)
            cur = []
        cur.append(t)
        prev = b
    if cur:
        blocks.append(cur)
    return blocks


@dataclass
class BlockFit:
    """Per-block correction summary for the report."""

    block: int
    n_trials: int
    n_anchors: int
    corrected: bool
    max_shift_ms: float = 0.0
    end_shift_ms: float = 0.0
    rate_ppm: float = 0.0


def correct_cue_onsets(
    anchors: dict[int, float],
    auditory_sec: list[float],
    trialinfo: list[dict],
    cue_onsets: list[float],
) -> tuple[list[float], list[BlockFit]]:
    """Re-map each trial's cue onset onto the true audio timeline using the per-block anchors.

    A block with <2 anchors is left unchanged (we can't fit its rate). Within an anchored block the
    map is piecewise-linear through ``(EDF-elapsed-since-block-start, true audio onset)`` — exact at
    2 anchors, bending at extra (anomaly) anchors.
    """
    corrected = list(cue_onsets)
    fits: list[BlockFit] = []
    for bi, bt in enumerate(_block_trials(trialinfo), start=1):
        a_trials = sorted(t for t in bt if t in anchors)
        if len(a_trials) < 2:
            fits.append(BlockFit(bi, len(bt), len(a_trials), corrected=False))
            continue
        aud_first = auditory_sec[bt[0] - 1]
        elapseds = np.array([auditory_sec[t - 1] - aud_first for t in a_trials])
        positions = np.array([anchors[t] for t in a_trials])
        shifts = []
        for t in bt:
            el = auditory_sec[t - 1] - aud_first
            new = float(np.interp(el, elapseds, positions))
            shifts.append(new - cue_onsets[t - 1])
            corrected[t - 1] = new
        span = elapseds[-1] - elapseds[0]
        rate = ((positions[-1] - positions[0]) / span - 1.0) * 1e6 if span > 0 else 0.0
        fits.append(
            BlockFit(
                bi,
                len(bt),
                len(a_trials),
                corrected=True,
                max_shift_ms=max(abs(s) for s in shifts) * 1000,
                end_shift_ms=shifts[-1] * 1000,
                rate_ppm=rate,
            )
        )
    return corrected, fits


def _backup(path: Path) -> None:
    """Preserve the pre-fix file once (never clobber an existing original backup)."""
    backup = path.with_name(path.stem + BACKUP_SUFFIX)
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)


def _rewrite_cue(path: Path, cue: Tier, corrected: list[float]) -> None:
    _backup(path)
    intervals = [
        Interval(on, on + CUE_DURATION, iv.label)
        for iv, on in zip(cue.intervals, corrected, strict=True)
    ]
    write_tier(Tier("cue_events", intervals), path)


def _rewrite_condition(path: Path, shifts: list[float]) -> None:
    """Shift each condition marker by the same correction its trial's cue got (preserves the
    cue→condition offset; the residual over the ~1.7 s gap is rate×1.7 s, negligible)."""
    cond = read_tier(path, "condition_events")
    if len(cond.intervals) != len(shifts):
        return  # structure we don't recognise — leave it alone
    _backup(path)
    intervals = [
        Interval(iv.start + s, iv.end + s, iv.label)
        for iv, s in zip(cond.intervals, shifts, strict=True)
    ]
    write_tier(Tier("condition_events", intervals), path)


def apply_clock_fix(results_dir: Path | str, trials_mat: Path | str) -> dict:
    """Read anchors + Trials + events, correct cue (and condition) events in place, return a report.

    Backs up the originals to ``*.before_clock_fix.txt`` (once). Raises ``ValueError`` on missing
    anchors or a Trials/trialInfo length mismatch.
    """
    results_dir = Path(results_dir)
    anchors = load_anchors(results_dir / paths.CLOCK_ANCHORS_TXT)
    if not anchors:
        raise ValueError("No clock anchors found (clock_anchors.txt is empty or unmarked).")
    trialinfo = load_trialinfo(results_dir / paths.TRIALINFO_MAT)
    trials = load_trials(trials_mat)
    if len(trials) != len(trialinfo):
        raise ValueError(
            f"Trials ({len(trials)}) and trialInfo ({len(trialinfo)}) length mismatch — "
            "resolve that before correcting clock drift."
        )
    cue_path = results_dir / paths.CUE_EVENTS_TXT
    cue = read_tier(cue_path, "cue_events")
    if len(cue.intervals) != len(trials):
        raise ValueError(
            f"cue_events ({len(cue.intervals)}) and Trials ({len(trials)}) length mismatch."
        )
    cue_onsets = [iv.start for iv in cue.intervals]
    auditory_sec = [float(tr["Auditory"]) / EDF_RATE for tr in trials]

    corrected, fits = correct_cue_onsets(anchors, auditory_sec, trialinfo, cue_onsets)
    _rewrite_cue(cue_path, cue, corrected)

    cond_path = results_dir / paths.CONDITION_EVENTS_TXT
    if cond_path.exists():
        shifts = [corrected[i] - cue_onsets[i] for i in range(len(cue_onsets))]
        _rewrite_condition(cond_path, shifts)

    return {
        "n_anchors": len(anchors),
        "blocks": fits,
        "corrected_blocks": sum(f.corrected for f in fits),
        "uncorrected_blocks": [f.block for f in fits if not f.corrected],
        "cue_path": cue_path,
    }


def reapply_if_present(results_dir: Path | str, trials_mat: Path | str) -> dict | None:
    """Re-apply a saved clock-drift fit if ``clock_anchors.txt`` exists with anchors, else ``None``.

    Steps that regenerate cue/condition events from the raw ``Trials.Auditory`` (make-events, the
    trigger-fix) would otherwise silently wipe a prior clock-drift correction. Calling this right
    after they write the events re-sticks the fit — it is idempotent, because the corrected onsets
    are a pure function of the anchors + ``Auditory`` + trialInfo, not of the current events (so
    correcting a freshly regenerated, drifted set reproduces the same result).
    """
    results_dir = Path(results_dir)
    path = results_dir / paths.CLOCK_ANCHORS_TXT
    if not path.exists() or not load_anchors(path):
        return None
    return apply_clock_fix(results_dir, trials_mat)
