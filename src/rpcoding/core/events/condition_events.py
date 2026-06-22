r"""Port of make_condition_events.m: condition (cue-type) events anchored to the cue events.

Per block, ``anchor`` = the audio-onset field of the block's first trial and ``onset`` = the cue
event onset (``cue_events`` column 1) of that first trial. Each trial's marker is
``cueStart - anchor + onset`` with a fixed 0.5 s duration. Labels are ``<trial>_<cue>`` where cue is
``Yes/No`` / ``Repeat`` / ``:=:``.

Reads the (possibly hand-adjusted) cue_events onsets, so it must run *after* cue events exist.
"""

from __future__ import annotations

from pathlib import Path

from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.matio import load_trialinfo, trial_audio_onset, trial_block, trial_cue

CONDITION_DURATION = 0.5  # seconds


def make_condition_events(trialinfo: list[dict], cue_onsets: list[float]) -> Tier:
    """Build the condition-events tier from trialInfo and the per-trial cue-event onsets."""
    if len(cue_onsets) != len(trialinfo):
        raise ValueError(
            f"cue_events ({len(cue_onsets)}) and trialInfo ({len(trialinfo)}) length mismatch"
        )
    intervals: list[Interval] = []
    b = 0
    anchor = 0.0
    onset = 0.0
    for t, ti in enumerate(trialinfo):
        block = int(round(float(trial_block(ti))))
        if block != b:
            b += 1
            anchor = float(trial_audio_onset(ti))
            onset = cue_onsets[t]
        on = float(ti["cueStart"]) - anchor + onset
        intervals.append(Interval(on, on + CONDITION_DURATION, f"{t + 1}_{trial_cue(ti)}"))
    return Tier("condition_events", intervals)


def generate_condition_events(results_dir: Path | str, out: Path | str | None = None) -> Tier:
    """Load trialInfo + cue_events from disk, build condition events, write condition_events.txt."""
    results_dir = Path(results_dir)
    trialinfo = load_trialinfo(results_dir / "trialInfo.mat")
    onsets = [iv.start for iv in read_tier(results_dir / "cue_events.txt")]
    tier = make_condition_events(trialinfo, onsets)
    write_tier(tier, out if out is not None else results_dir / "condition_events.txt")
    return tier
