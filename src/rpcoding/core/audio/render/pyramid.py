"""Waveform min/max LOD pyramid: build, level selection, and visible-window slicing.

A pyramid stores, per level, ``(n_bins, 2)`` float32 columns ``[min, max]`` over a
power-of-``decim`` decimation. Level 0 = ``BASE_DECIM`` samples/bin; each higher level decimates
by ``LEVEL_FACTOR`` until fewer than ``MIN_BINS`` bins remain. For 135M samples that's ~6-8
levels, ~6 MB total. Below level 0 (zoomed past 256 samples/pixel) the caller reads raw samples
from the wav window (``pick_level`` -> -1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BASE_DECIM = 256
LEVEL_FACTOR = 4
MIN_BINS = 1024
PYRAMID_VERSION = 1


@dataclass(frozen=True)
class WaveformPyramid:
    levels: list[np.ndarray]  # each (n_bins, 2) float32: col 0 = min, col 1 = max
    decims: list[int]
    n_samples: int
    fs: int


def _bin_starts(n: int, decim: int) -> np.ndarray:
    nbins = (n + decim - 1) // decim
    starts = np.arange(nbins, dtype=np.int64) * decim
    return starts[starts < n]


def _level0_from_samples(x: np.ndarray, decim: int) -> tuple[np.ndarray, np.ndarray]:
    starts = _bin_starts(len(x), decim)
    mn = np.minimum.reduceat(x, starts).astype(np.float32)
    mx = np.maximum.reduceat(x, starts).astype(np.float32)
    return mn, mx


def _minmax_decimate(mn: np.ndarray, mx: np.ndarray, factor: int) -> tuple[np.ndarray, np.ndarray]:
    starts = _bin_starts(len(mn), factor)
    return (
        np.minimum.reduceat(mn, starts).astype(np.float32),
        np.maximum.reduceat(mx, starts).astype(np.float32),
    )


def _pyramid_from_level0(
    mn0: np.ndarray, mx0: np.ndarray, n_samples: int, fs: int
) -> WaveformPyramid:
    levels = [np.stack([mn0, mx0], axis=1)]
    decims = [BASE_DECIM]
    mn, mx = mn0, mx0
    while len(mn) > MIN_BINS:
        mn, mx = _minmax_decimate(mn, mx, LEVEL_FACTOR)
        levels.append(np.stack([mn, mx], axis=1))
        decims.append(decims[-1] * LEVEL_FACTOR)
    return WaveformPyramid(levels=levels, decims=decims, n_samples=n_samples, fs=fs)


def build_pyramid(x: np.ndarray, fs: int) -> WaveformPyramid:
    """Build a pyramid from an in-RAM signal (used in tests / small arrays)."""
    x = np.ascontiguousarray(x, dtype=np.float32)
    mn0, mx0 = _level0_from_samples(x, BASE_DECIM)
    return _pyramid_from_level0(mn0, mx0, len(x), fs)


def build_pyramid_streaming(wav_path, progress=None) -> WaveformPyramid:
    """Build a pyramid by streaming blocks (peak RAM = one block, never the full float64 signal)."""
    import soundfile as sf

    from rpcoding.core.audio.io import stream_blocks

    info = sf.info(str(wav_path))
    total = info.frames
    blocksize = (
        BASE_DECIM * 8192
    )  # multiple of BASE_DECIM so bins never straddle blocks (~2M samples)
    mn_parts: list[np.ndarray] = []
    mx_parts: list[np.ndarray] = []
    done = 0
    for block in stream_blocks(wav_path, blocksize):
        mn, mx = _level0_from_samples(block, BASE_DECIM)
        mn_parts.append(mn)
        mx_parts.append(mx)
        done += len(block)
        if progress is not None and total:
            progress(int(100 * done / total), "Building waveform")
    mn0 = np.concatenate(mn_parts) if mn_parts else np.zeros(0, np.float32)
    mx0 = np.concatenate(mx_parts) if mx_parts else np.zeros(0, np.float32)
    return _pyramid_from_level0(mn0, mx0, total, info.samplerate)


def pick_level(
    decims: list[int], x0: float, x1: float, px_w: int, samples_per_px_target: float = 1.5
) -> int:
    """Coarsest level with ``decim <= samples_per_pixel / target``; -1 means slice raw samples."""
    if px_w <= 0 or x1 <= x0:
        return -1
    target = ((x1 - x0) / px_w) / samples_per_px_target
    best = -1
    for i, d in enumerate(decims):
        if d <= target:
            best = i
    return best


def slice_level(
    pyr: WaveformPyramid, lvl: int, x0: float, x1: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Slice a level to the visible window (+/-1 bin). Returns (bin_centers_samples, mn, mx)."""
    if lvl < 0:
        raise ValueError("level -1 (raw) must be read from the wav by the caller")
    d = pyr.decims[lvl]
    arr = pyr.levels[lvl]
    b0 = max(int(x0 // d) - 1, 0)
    b1 = min(int(x1 // d) + 2, len(arr))
    sub = arr[b0:b1]
    centers = np.arange(b0, b1, dtype=np.float64) * d + d / 2.0
    return centers, sub[:, 0], sub[:, 1]
