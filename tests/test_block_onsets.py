"""Tests for the block-onset navigation tier."""

from __future__ import annotations

import numpy as np

from rpcoding.core.audio.concat import load_block_wav_onsets, save_block_wav_onsets
from rpcoding.core.events.block_onsets import load_block_onsets_tier, make_block_onsets_tier


def test_make_block_onsets_tier_times_and_labels():
    # block 1 @ sample 1 (t=0), block 2 missing (zero row), block 3 @ sample 5001 (t=5.0)
    onsets = np.array([[1.0, 1000.0], [0.0, 0.0], [5001.0, 1000.0]])
    tier = make_block_onsets_tier(onsets, marker_seconds=1.0)
    assert [iv.label for iv in tier.intervals] == ["block 1", "block 3"]
    assert tier.intervals[0].start == 0.0
    assert tier.intervals[0].end == 1.0
    assert tier.intervals[1].start == 5.0  # (5001 - 1) / 1000
    assert tier.name == "block_onsets"


def test_make_block_onsets_tier_single_block_squeezed():
    # a single-block file can come back squeezed to shape (2,) -> atleast_2d restores the row
    tier = make_block_onsets_tier(np.array([1.0, 2000.0]))
    assert [iv.label for iv in tier.intervals] == ["block 1"]
    assert tier.intervals[0].start == 0.0


def test_make_block_onsets_tier_empty():
    assert make_block_onsets_tier(np.zeros((4, 2))).intervals == []


def test_block_wav_onsets_round_trip(tmp_path):
    onsets = np.array([[1.0, 1000.0], [3001.0, 1000.0]])
    p = tmp_path / "block_wav_onsets.mat"
    save_block_wav_onsets(p, onsets)
    np.testing.assert_array_equal(load_block_wav_onsets(p), onsets)


def test_load_block_onsets_tier_absent_is_empty(tmp_path):
    assert load_block_onsets_tier(tmp_path).intervals == []


def test_load_block_onsets_tier_from_mat(tmp_path):
    save_block_wav_onsets(
        tmp_path / "block_wav_onsets.mat", np.array([[1.0, 1000.0], [4001.0, 1000.0]])
    )
    tier = load_block_onsets_tier(tmp_path)
    assert [iv.label for iv in tier.intervals] == ["block 1", "block 2"]
    assert tier.intervals[1].start == 4.0  # (4001 - 1) / 1000
