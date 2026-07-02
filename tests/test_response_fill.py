"""Tests for filling MFA-dropped response rows with Omitted/NOISY placeholders."""

from __future__ import annotations

import numpy as np
import scipy.io as sio

from rpcoding.core.labels import Interval, Tier, write_tier
from rpcoding.core.rpcode.response_fill import (
    NOISY,
    OMITTED,
    build_response_tier,
    count_omitted,
    fill_response_intervals,
)
from rpcoding.core.tasks import Task


def _save_trialinfo(path, trials):
    """trials: list of (cue, omission) -> a 1xN struct array trialInfo.mat."""
    arr = np.zeros((1, len(trials)), dtype=[("cue", "O"), ("Omission", "O")])
    for i, (cue, om) in enumerate(trials):
        arr[0, i]["cue"] = cue
        arr[0, i]["Omission"] = om
    sio.savemat(str(path), {"trialInfo": arr})


def test_fill_keeps_aligned_else_placeholder():
    aligned = [Interval(0.5, 1.5, "resp0"), None, Interval(4.2, 5.0, "resp2")]
    out = fill_response_intervals(aligned, [(0, 2), (2, 4), (4, 6)], [False, True, False])
    assert [iv.label for iv in out] == ["resp0", OMITTED, "resp2"]
    assert (out[0].start, out[0].end) == (0.5, 1.5)  # aligned kept verbatim
    assert (out[1].start, out[1].end) == (2, 4)  # placeholder sits at the trial's window


def test_fill_noisy_when_not_responded():
    assert fill_response_intervals([None], [(0, 2)], [False])[0].label == NOISY


def test_fill_omitted_when_responded():
    assert fill_response_intervals([None], [(0, 2)], [True])[0].label == OMITTED


def test_count_omitted():
    ivs = [Interval(0, 1, "a"), Interval(1, 2, "Omitted"), Interval(2, 3, NOISY)]
    ivs.append(Interval(3, 4, " Omitted "))  # whitespace-padded still counts
    assert count_omitted(ivs) == 2


def test_build_response_tier_missing_inputs_is_none(tmp_path):
    assert build_response_tier(tmp_path, task=Task.LEXICAL_NODELAY) is None


def test_build_response_tier_cue_count_mismatch_is_none(tmp_path):
    write_tier(Tier("c", [Interval(0, 1, "1_a")]), tmp_path / "cue_events.txt")  # 1 onset
    _save_trialinfo(tmp_path / "trialInfo.mat", [("Repeat", "x"), ("Repeat", "x")])  # != 2 trials
    assert build_response_tier(tmp_path, task=Task.LEXICAL_NODELAY) is None


def test_build_response_tier_end_to_end(tmp_path):
    mfa = tmp_path / "mfa"
    mfa.mkdir()
    # 3 Repeat trials with cue onsets at 0 / 2 / 4 s
    write_tier(
        Tier("c", [Interval(0, 1, "1_a"), Interval(2, 3, "2_b"), Interval(4, 5, "3_c")]),
        tmp_path / "cue_events.txt",
    )
    write_tier(
        Tier("w", [Interval(0.1, 1.9, "s0"), Interval(2.1, 3.9, "s1"), Interval(4.1, 5.9, "s2")]),
        mfa / "annotated_resp_windows.txt",
    )
    # MFA aligned trials 0 and 2; trial 1 (onset 2 s) has no response -> placeholder
    write_tier(
        Tier("r", [Interval(0.5, 1.5, "r0"), Interval(4.2, 5.0, "r2")]), mfa / "mfa_resp_words.txt"
    )
    _save_trialinfo(
        tmp_path / "trialInfo.mat",
        [("Repeat", "No Response"), ("Repeat", "Responded"), ("Repeat", "No Response")],
    )
    tier = build_response_tier(tmp_path, task=Task.LEXICAL_NODELAY)
    assert [iv.label for iv in tier.intervals] == ["r0", OMITTED, "r2"]
    assert (tier.intervals[1].start, tier.intervals[1].end) == (2.1, 3.9)  # placeholder at window
    assert len(tier.intervals) == 3  # one per Repeat trial


def test_build_response_tier_phoneme_sequencing_all_trials(tmp_path):
    mfa = tmp_path / "mfa"
    mfa.mkdir()
    # PS: every trial is a spoken "Listen" repeat (1:1); cue onsets at 0 / 2 / 4 s.
    write_tier(
        Tier("c", [Interval(0, 1, "1_a"), Interval(2, 3, "2_b"), Interval(4, 5, "3_c")]),
        tmp_path / "cue_events.txt",
    )
    write_tier(
        Tier("w", [Interval(0.1, 1.9, "s0"), Interval(2.1, 3.9, "s1"), Interval(4.1, 5.9, "s2")]),
        mfa / "annotated_resp_windows.txt",
    )
    # MFA aligned trials 0 and 2; trial 1 dropped -> Omitted (PS always responds, even if the log
    # says "No Response"), NOT NOISY -- the key difference from the NoDelay/UP behaviour above.
    write_tier(
        Tier("r", [Interval(0.5, 1.5, "r0"), Interval(4.2, 5.0, "r2")]), mfa / "mfa_resp_words.txt"
    )
    _save_trialinfo(
        tmp_path / "trialInfo.mat",
        [("Listen", "No Response"), ("Listen", "No Response"), ("Listen", "No Response")],
    )
    tier = build_response_tier(tmp_path, task=Task.PHONEME_SEQUENCING)
    assert [iv.label for iv in tier.intervals] == ["r0", OMITTED, "r2"]
    assert len(tier.intervals) == 3  # one per trial (every PS trial is production)
