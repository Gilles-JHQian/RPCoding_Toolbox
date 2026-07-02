"""Tests for the time -> trial mapping (pure)."""

from __future__ import annotations

from rpcoding.core.labels import Interval, Tier
from rpcoding.core.trial_index import TrialIndex, parse_trial_label


def test_parse_trial_label():
    assert parse_trial_label("1_jural.wav") == (1, "jural.wav")
    assert parse_trial_label("2_Yes/No") == (2, "Yes/No")
    assert parse_trial_label("noisy") == (None, "noisy")


def test_trial_index_lookup():
    cue = Tier("cue", [Interval(4.0, 5.0, "1_jural.wav"), Interval(10.0, 11.0, "2_basin.wav")])
    cond = Tier("cond", [Interval(2.0, 2.5, "1_Yes/No"), Interval(8.0, 8.5, "2_Repeat")])
    ti = TrialIndex(cue, cond)

    assert len(ti) == 2
    info = ti.at(4.5)
    assert info.trial == 1 and info.stim == "jural.wav" and info.task == "Yes/No"
    assert ti.at(10.5).trial == 2 and ti.at(10.5).task == "Repeat"
    assert ti.at(99.0).trial == 2  # latest trial holds after its onset
    assert ti.at(0.0) is None  # before the first cue


def test_trial_index_without_condition():
    cue = Tier("cue", [Interval(4.0, 5.0, "1_x.wav")])
    ti = TrialIndex(cue)
    assert ti.at(4.5).task is None and ti.at(4.5).stim == "x.wav"


def _three_trials() -> TrialIndex:
    return TrialIndex(
        Tier("cue", [Interval(4.0, 5.0, "1_a.wav"),
                     Interval(10.0, 11.0, "2_b.wav"),
                     Interval(16.0, 17.0, "3_c.wav")])
    )


def test_overlapping_picks_most_overlap():
    ti = _three_trials()
    assert ti.overlapping(4.2, 4.9).trial == 1  # inside trial 1's box
    assert ti.overlapping(10.5, 12.0).trial == 2  # overlaps trial 2's box most
    # straddles trial 2/3 boxes -> the one with the larger overlap
    assert ti.overlapping(10.2, 16.2).trial == 2  # 0.8 of box 2 vs 0.2 of box 3
    assert ti.overlapping(10.9, 16.8).trial == 3  # 0.1 of box 2 vs 0.8 of box 3


def test_overlapping_falls_back_to_nearest_when_no_overlap():
    ti = _three_trials()
    # a selection in the gap just before trial 2's drifted box -> nearest is trial 2
    assert ti.overlapping(9.0, 9.6).trial == 2
    # just after trial 1's box, closer to 1 than 2
    assert ti.overlapping(5.4, 5.8).trial == 1
    assert ti.overlapping(0.0, 1.0).trial == 1  # before everything -> first trial (nearest)


def test_overlapping_handles_reversed_span_and_empty():
    ti = _three_trials()
    assert ti.overlapping(4.9, 4.2).trial == 1  # t0 > t1 tolerated
    assert TrialIndex(Tier("cue", [])).overlapping(1.0, 2.0) is None
