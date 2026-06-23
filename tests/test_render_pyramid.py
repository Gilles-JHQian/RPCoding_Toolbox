"""Tests for the waveform min/max LOD pyramid (pure numpy)."""

from __future__ import annotations

import numpy as np

from rpcoding.core.audio.render.pyramid import (
    MIN_BINS,
    _level0_from_samples,
    build_pyramid,
    pick_level,
    slice_level,
)


def test_level0_minmax_exact_with_ragged_tail():
    x = np.arange(1000, dtype=np.float32)
    mn, mx = _level0_from_samples(x, 256)
    assert mn.shape[0] == (1000 + 255) // 256  # ceil = 4 bins
    assert mn[0] == 0 and mx[0] == 255
    assert mn[-1] == 768 and mx[-1] == 999  # partial last bin


def test_level_count_and_decims():
    p = build_pyramid(np.zeros(2_000_000, np.float32), 1000)
    assert p.decims[0] == 256
    assert all(p.decims[i + 1] == p.decims[i] * 4 for i in range(len(p.decims) - 1))
    assert len(p.levels[-1]) <= MIN_BINS


def test_known_spike_survives_all_levels():
    x = np.zeros(2_000_000, np.float32)
    x[123_456] = 5.0
    p = build_pyramid(x, 1000)
    for lv in p.levels:
        assert lv[:, 1].max() == 5.0  # max envelope preserved at every level


def test_coarse_bin_brackets_finer():
    rng = np.random.default_rng(0)
    p = build_pyramid(rng.standard_normal(500_000).astype(np.float32), 1000)
    l0, l1 = p.levels[0], p.levels[1]
    assert l1[0, 0] <= l0[:4, 0].min() + 1e-6  # min bound
    assert l1[0, 1] >= l0[:4, 1].max() - 1e-6  # max bound


def test_dtype_finite():
    rng = np.random.default_rng(1)
    p = build_pyramid(rng.standard_normal(300_000).astype(np.float32), 1000)
    for lv in p.levels:
        assert lv.dtype == np.float32 and np.isfinite(lv).all()


def test_pick_level_coarsest_valid_and_raw():
    decims = [256, 1024, 4096, 16384]
    lvl = pick_level(decims, 0, 2_000_000, 1000)  # spp=2000 -> coarsest decim <= 2000 == 1024
    assert decims[lvl] <= 2000
    if lvl + 1 < len(decims):
        assert decims[lvl + 1] > 2000
    # a 10 s-ish window (spp ~ 294) still uses level 0, not raw
    assert pick_level(decims, 0, 441_000, 1500) == 0
    assert pick_level(decims, 0, 300, 1000) == -1  # zoomed in past level 0 -> raw


def test_slice_window_only():
    p = build_pyramid(np.zeros(2_000_000, np.float32), 1000)
    centers, mn, mx = slice_level(p, 1, 100_000, 200_000)
    assert len(centers) == len(mn) == len(mx)
    assert centers[0] <= 100_000  # padded one bin before
    assert centers[-1] >= 200_000 - p.decims[1]  # covers the window
