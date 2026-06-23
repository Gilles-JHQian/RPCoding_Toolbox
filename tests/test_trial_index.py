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
