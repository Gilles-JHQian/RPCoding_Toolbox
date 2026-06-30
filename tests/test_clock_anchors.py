"""Tests for the clock-drift fix gadget's anchor seeding (headless — no Qt)."""

from __future__ import annotations

from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.trialinfo.build import save_trialinfo
from rpcoding.gui.editor_loader import (
    _block_boundary_trials,
    _trial_num,
    tiers_for_clock_anchors,
)


def test_trial_num():
    assert _trial_num("120_kaenahstay.wav") == 120
    assert _trial_num("7") == 7
    assert _trial_num("3 start") == 3
    assert _trial_num("") is None
    assert _trial_num("nope") is None


def test_block_boundary_trials():
    ti = [{"block": float(b)} for b in (1, 1, 1, 2, 2, 3)]
    assert _block_boundary_trials(ti) == [(1, 3), (4, 5), (6, 6)]
    assert _block_boundary_trials([]) == []


def _clock_tier(specs):
    return next(t for n, t, _e in specs if n == "clock_anchors")


def test_seed_anchors_at_block_first_and_last(tmp_path):
    rd = tmp_path / "D9"
    rd.mkdir()
    write_tier(
        Tier(
            "cue_events",
            [
                Interval(10.0, 11.0, "1_a.wav"),
                Interval(14.0, 15.0, "2_b.wav"),
                Interval(100.0, 101.0, "3_c.wav"),
                Interval(104.0, 105.0, "4_d.wav"),
            ],
        ),
        rd / "cue_events.txt",
    )
    save_trialinfo(rd / "trialInfo.mat", [{"block": float(b)} for b in (1, 1, 2, 2)])

    specs, save_path = tiers_for_clock_anchors(rd)
    assert save_path == rd / "clock_anchors.txt"
    assert any(n == "clock_anchors" and editable for n, _t, editable in specs)
    anchors = _clock_tier(specs)
    # block 1 -> trials 1 & 2, block 2 -> trials 3 & 4, each placed at its cue onset
    assert [iv.label for iv in anchors.intervals] == ["1", "2", "3", "4"]
    assert [iv.start for iv in anchors.intervals] == [10.0, 14.0, 100.0, 104.0]


def test_resume_from_saved_anchors(tmp_path):
    rd = tmp_path / "D9"
    rd.mkdir()
    write_tier(Tier("clock_anchors", [Interval(5.0, 5.05, "120")]), rd / "clock_anchors.txt")
    specs, _ = tiers_for_clock_anchors(rd)  # no cue/trialInfo -> still loads the saved file
    assert [iv.label for iv in _clock_tier(specs).intervals] == ["120"]


def test_seed_empty_without_cue_or_trialinfo(tmp_path):
    rd = tmp_path / "D9"
    rd.mkdir()
    specs, _ = tiers_for_clock_anchors(rd)
    assert _clock_tier(specs).intervals == []


def test_saved_anchors_roundtrip(tmp_path):
    # what the editor would write, and what the algorithm (branch 2) will read back
    rd = tmp_path / "D9"
    rd.mkdir()
    write_tier(
        Tier("clock_anchors", [Interval(3.2, 3.25, "1"), Interval(540.7, 540.75, "120")]),
        rd / "clock_anchors.txt",
    )
    got = read_tier(rd / "clock_anchors.txt", "clock_anchors")
    assert [(round(iv.start, 2), iv.label) for iv in got.intervals] == [(3.2, "1"), (540.7, "120")]
