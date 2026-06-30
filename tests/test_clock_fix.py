"""Tests for the clock-drift correction algorithm (core.clock_fix)."""

from __future__ import annotations

import pytest

from rpcoding.core.clock_fix import (
    EDF_RATE,
    _block_trials,
    apply_clock_fix,
    correct_cue_onsets,
    load_anchors,
)
from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.rpcode.rpcode2trials import save_trials
from rpcoding.core.trialinfo.build import save_trialinfo


def test_load_anchors(tmp_path):
    write_tier(
        Tier("clock_anchors", [Interval(3.2, 3.25, "1"), Interval(540.7, 540.75, "120 end")]),
        tmp_path / "a.txt",
    )
    assert load_anchors(tmp_path / "a.txt") == {1: 3.2, 120: 540.7}


def test_block_trials():
    ti = [{"block": float(b)} for b in (1, 1, 1, 2, 2, 2)]
    assert _block_trials(ti) == [[1, 2, 3], [4, 5, 6]]


def test_correct_cue_onsets_linear():
    # block 1 drifts at rate 1.5 (audio elapsed = 1.5 x EDF elapsed); block 2 the same
    auditory_sec = [0, 4, 8, 100, 104, 108]
    trialinfo = [{"block": float(b)} for b in (1, 1, 1, 2, 2, 2)]
    cue_onsets = [10, 14, 18, 200, 204, 208]  # = first_stim + EDF elapsed
    anchors = {1: 10.0, 3: 22.0, 4: 200.0, 6: 212.0}  # true positions (start/end of each block)
    corrected, fits = correct_cue_onsets(anchors, auditory_sec, trialinfo, cue_onsets)
    assert corrected == [10, 16, 22, 200, 206, 212]  # middle trial interpolated onto the true line
    assert all(f.corrected for f in fits)
    assert round(fits[0].rate_ppm) == 500000  # (1.5 - 1) x 1e6


def test_block_without_two_anchors_is_left_alone():
    auditory_sec = [0, 4, 8]
    trialinfo = [{"block": 1.0}] * 3
    cue_onsets = [10, 14, 18]
    corrected, fits = correct_cue_onsets({1: 10.0}, auditory_sec, trialinfo, cue_onsets)
    assert corrected == [10, 14, 18]
    assert fits[0].corrected is False and fits[0].n_anchors == 1


def test_nonlinear_block_bends_at_anomaly_anchor():
    # one extra interior anchor -> piecewise-linear, not a single slope
    auditory_sec = [0, 4, 8, 12]
    trialinfo = [{"block": 1.0}] * 4
    cue_onsets = [0, 4, 8, 12]
    anchors = {1: 0.0, 2: 4.0, 4: 100.0}  # flat to trial 2, then a big jump (a "step")
    corrected, _ = correct_cue_onsets(anchors, auditory_sec, trialinfo, cue_onsets)
    assert corrected[0] == 0 and corrected[1] == 4
    assert corrected[2] == pytest.approx(52.0)  # halfway between anchors at trials 2 and 4
    assert corrected[3] == 100


def _write_trials(path, auditory_secs):
    save_trials(
        path, [{"Trial": i + 1, "Auditory": s * EDF_RATE} for i, s in enumerate(auditory_secs)]
    )


def test_apply_clock_fix_end_to_end(tmp_path):
    rd = tmp_path / "D9"
    rd.mkdir()
    aud = [0, 4, 8, 100, 104, 108]
    save_trialinfo(rd / "trialInfo.mat", [{"block": float(b)} for b in (1, 1, 1, 2, 2, 2)])
    _write_trials(tmp_path / "Trials.mat", aud)
    cue = [10, 14, 18, 200, 204, 208]
    write_tier(
        Tier("cue_events", [Interval(o, o + 1, f"{i + 1}_x.wav") for i, o in enumerate(cue)]),
        rd / "cue_events.txt",
    )
    write_tier(
        Tier(
            "condition_events",
            [Interval(o - 1.7, o - 1.2, f"{i + 1}_Repeat") for i, o in enumerate(cue)],
        ),
        rd / "condition_events.txt",
    )
    write_tier(
        Tier(
            "clock_anchors",
            [
                Interval(t, t + 0.05, lab)
                for t, lab in [(10, "1"), (22, "3"), (200, "4"), (212, "6")]
            ],
        ),
        rd / "clock_anchors.txt",
    )
    report = apply_clock_fix(rd, tmp_path / "Trials.mat")

    out = read_tier(rd / "cue_events.txt", "cue_events")
    assert [round(iv.start, 2) for iv in out.intervals] == [10, 16, 22, 200, 206, 212]
    assert (rd / "cue_events.before_clock_fix.txt").exists()  # original backed up
    # condition shifted by the same per-trial correction (trial 2: +2 s)
    cond = read_tier(rd / "condition_events.txt", "condition_events")
    assert round(cond.intervals[1].start, 2) == round(14 - 1.7 + 2, 2)
    assert (rd / "condition_events.before_clock_fix.txt").exists()
    assert report["corrected_blocks"] == 2 and report["uncorrected_blocks"] == []


def test_apply_clock_fix_requires_anchors(tmp_path):
    rd = tmp_path / "D9"
    rd.mkdir()
    write_tier(Tier("clock_anchors", []), rd / "clock_anchors.txt")
    with pytest.raises(ValueError, match="No clock anchors"):
        apply_clock_fix(rd, tmp_path / "Trials.mat")
