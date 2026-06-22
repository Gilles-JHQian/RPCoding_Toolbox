r"""Port of make_cue_events_lr.m: stimulus cue events from EDF timing + first-stim anchors.

Per block, the EDF auditory timestamp of the block's first trial anchors the block; each trial's
onset is ``first_stims_onset[block] + (Trials[t].Auditory - block_anchor) / 30000`` seconds, with a
fixed 1.0 s cue duration. Labels are ``<trial>_<sound>``.

Requires the external ``Trials.mat`` (``.Auditory`` EDF ticks @ 30 kHz);
``len(Trials)`` must equal ``len(trialInfo)``.
"""

from __future__ import annotations

from pathlib import Path

from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.matio import load_trialinfo, load_trials, trial_block, trial_stim

EDF_RATE = 3e4  # EDF clock ticks per second
CUE_DURATION = 1.0  # seconds


def make_cue_events(
    trialinfo: list[dict], trials: list[dict], first_stims_onsets: list[float]
) -> Tier:
    """Build the cue-events tier from trialInfo, Trials (EDF), and per-block first-stim onsets."""
    if len(trials) != len(trialinfo):
        raise ValueError(f"Trials ({len(trials)}) and trialInfo ({len(trialinfo)}) length mismatch")
    intervals: list[Interval] = []
    b = 0  # block counter (1-based once incremented), faithful to the MATLAB
    edf_first = 0.0
    for t, (ti, tr) in enumerate(zip(trialinfo, trials, strict=True)):
        block = int(round(float(trial_block(ti))))
        if block != b:
            b += 1
            edf_first = float(tr["Auditory"])
        if b - 1 >= len(first_stims_onsets):
            raise IndexError(
                f"first_stims has {len(first_stims_onsets)} block(s); "
                f"trial {t + 1} is in block {b}"
            )
        on = first_stims_onsets[b - 1] + (float(tr["Auditory"]) - edf_first) / EDF_RATE
        stim = trial_stim(ti)
        if stim is None:
            raise ValueError(f"trial {t + 1}: trialInfo has no 'sound'/'stim' field")
        intervals.append(Interval(on, on + CUE_DURATION, f"{t + 1}_{stim}"))
    return Tier("cue_events", intervals)


def generate_cue_events(
    results_dir: Path | str, trials_mat: Path | str, out: Path | str | None = None
) -> Tier:
    """Load trialInfo/Trials/first_stims from disk, build cue events, and write cue_events.txt."""
    results_dir = Path(results_dir)
    trialinfo = load_trialinfo(results_dir / "trialInfo.mat")
    trials = load_trials(trials_mat)
    onsets = [iv.start for iv in read_tier(results_dir / "first_stims.txt")]
    tier = make_cue_events(trialinfo, trials, onsets)
    write_tier(tier, out if out is not None else results_dir / "cue_events.txt")
    return tier
