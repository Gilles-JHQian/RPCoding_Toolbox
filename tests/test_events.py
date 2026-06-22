"""Tests for cue/condition event generation (make_cue_events_lr / make_condition_events ports)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpcoding.core.events.condition_events import make_condition_events
from rpcoding.core.events.cue_events import make_cue_events
from rpcoding.core.labels import read_tier
from rpcoding.core.matio import load_trials, trial_block
from rpcoding.core.paths import find_trials_mat
from rpcoding.core.trialinfo.build import discover_trialdata_files, select_and_combine

# ---- synthetic unit tests (always run) ----


def test_make_cue_events_math():
    trialinfo = [
        {"block": 1.0, "sound": "s0.wav"},
        {"block": 1.0, "sound": "s1.wav"},
        {"block": 2.0, "sound": "s2.wav"},
        {"block": 2.0, "sound": "s3.wav"},
    ]
    trials = [{"Auditory": 0.0}, {"Auditory": 3e4}, {"Auditory": 6e4}, {"Auditory": 7.5e4}]
    tier = make_cue_events(trialinfo, trials, [100.0, 200.0])

    assert [iv.start for iv in tier] == pytest.approx([100.0, 101.0, 200.0, 200.5])
    assert [iv.end for iv in tier] == pytest.approx([101.0, 102.0, 201.0, 201.5])
    assert [iv.label for iv in tier] == ["1_s0.wav", "2_s1.wav", "3_s2.wav", "4_s3.wav"]


def test_cue_events_length_mismatch():
    with pytest.raises(ValueError, match="length mismatch"):
        make_cue_events([{"block": 1.0, "sound": "x"}], [], [0.0])


def test_make_condition_events_math():
    trialinfo = [
        {"block": 1.0, "cueStart": 1000.0, "stimulusAudioStart": 1002.0, "cue": "Yes/No"},
        {"block": 1.0, "cueStart": 1005.0, "stimulusAudioStart": 1003.0, "cue": "Repeat"},
        {"block": 2.0, "cueStart": 2000.0, "stimulusAudioStart": 2001.0, "cue": ":=:"},
    ]
    tier = make_condition_events(trialinfo, [10.0, 11.0, 50.0])

    # block anchor (audio onset + cue onset) is fixed at the block's first trial
    assert [iv.start for iv in tier] == pytest.approx([8.0, 13.0, 49.0])
    assert [iv.end for iv in tier] == pytest.approx([8.5, 13.5, 49.5])
    assert [iv.label for iv in tier] == ["1_Yes/No", "2_Repeat", "3_:=:"]


def test_condition_events_cue_fallback_to_condition():
    trialinfo = [{"block": 1.0, "cueStart": 5.0, "stimulusAudioStart": 5.0, "condition": "Repeat"}]
    tier = make_condition_events(trialinfo, [0.0])
    assert tier.intervals[0].label == "1_Repeat"


# ---- real-data golden tests (skipped when Box isn't synced) ----

_BOX = Path("F:/CloudStorage/Box/CoganLab")
_RESULTS = (
    _BOX / "ECoG_Task_Data" / "response_coding" / "response_coding_results" / "LexicalDecRepNoDelay"
)
_CTD = _BOX / "ECoG_Task_Data" / "Cogan_Task_Data"
_DDATA = _BOX / "D_Data" / "LexicalDecRepNoDelay"


def _reconstructed_trialinfo(subject):
    """The full 504-trial trialInfo, rebuilt from TrialData (the lab's saved copy is incomplete)."""
    all_blocks = _CTD / subject / "Lexical No Delay" / "All Blocks"
    combined, _ = select_and_combine(discover_trialdata_files(all_blocks))
    return combined


@pytest.mark.skipif(not _RESULTS.exists(), reason="CoganLab data not synced locally")
@pytest.mark.parametrize("subject", ["D134", "D140"])
def test_real_condition_events_exact(subject):
    """condition_events isn't hand-edited, so our port must reproduce the lab's file exactly."""
    rdir = _RESULTS / subject
    trialinfo = _reconstructed_trialinfo(subject)
    cue_onsets = [iv.start for iv in read_tier(rdir / "cue_events.txt")]
    tier = make_condition_events(trialinfo, cue_onsets)
    lab = read_tier(rdir / "condition_events.txt")

    assert len(tier) == len(lab)
    for mine, ref in zip(tier, lab, strict=True):
        assert mine.label == ref.label
        assert abs(mine.start - ref.start) < 1e-6
        assert abs(mine.end - ref.end) < 1e-6


@pytest.mark.skipif(not _RESULTS.exists(), reason="CoganLab data not synced locally")
@pytest.mark.parametrize("subject", ["D134", "D140"])
def test_real_cue_events(subject):
    """Labels + per-block first-stim anchoring must be exact; times close to the hand-tuned file."""
    rdir = _RESULTS / subject
    trialinfo = _reconstructed_trialinfo(subject)
    trials = load_trials(find_trials_mat(_DDATA / subject))
    onsets = [iv.start for iv in read_tier(rdir / "first_stims.txt")]
    tier = make_cue_events(trialinfo, trials, onsets)
    lab = read_tier(rdir / "cue_events.txt")

    assert len(tier) == len(lab)
    assert [iv.label for iv in tier] == [iv.label for iv in lab]

    # each block's first trial is anchored exactly at its first_stims onset
    b = 0
    for t, ti in enumerate(trialinfo):
        block = int(round(float(trial_block(ti))))
        if block != b:
            b += 1
            assert abs(tier.intervals[t].start - onsets[b - 1]) < 1e-6

    # generated (pre-adjustment) onsets stay close to the hand-tuned ones
    diffs = sorted(abs(m.start - r.start) for m, r in zip(tier, lab, strict=True))
    assert diffs[len(diffs) // 2] < 0.25  # median
