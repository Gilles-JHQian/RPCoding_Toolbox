r"""A read-only navigation tier marking each block's onset in the concatenated ``allblocks.wav``.

Derived on the fly from ``block_wav_onsets.mat`` (written by :mod:`rpcoding.core.audio.concat`),
so it needs no extra pipeline artifact and works for any already-concatenated subject. It is purely
a navigation aid for the manual steps (jump to a block, then mark its first stimulus); it is never
edited or saved.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rpcoding.core import paths
from rpcoding.core.audio.concat import load_block_wav_onsets
from rpcoding.core.labels import Interval, Tier

BLOCK_ONSETS_TIER = "block_onsets"
MARKER_SECONDS = 1.0  # visible width of each onset marker


def make_block_onsets_tier(
    onsets: np.ndarray, *, marker_seconds: float = MARKER_SECONDS, name: str = BLOCK_ONSETS_TIER
) -> Tier:
    """Build the block-onset tier from the ``(max_block, 2)`` [1-based start sample, fs] array.

    Zero rows (block numbers absent from the recording) are skipped; each remaining block ``n`` gets
    a ``marker_seconds`` interval at ``(start_sample - 1) / fs`` labelled ``block <n>``.
    """
    arr = np.atleast_2d(np.asarray(onsets, dtype=np.float64))
    intervals: list[Interval] = []
    for i in range(arr.shape[0]):
        start_sample = arr[i, 0]
        fs = arr[i, 1] if arr.shape[1] > 1 else 0.0
        if start_sample <= 0 or fs <= 0:
            continue  # missing block (zero row)
        onset = (start_sample - 1.0) / fs  # 1-based sample index -> seconds
        intervals.append(Interval(onset, onset + marker_seconds, f"block {i + 1}"))
    return Tier(name, intervals)


def load_block_onsets_tier(results_dir: Path | str, *, name: str = BLOCK_ONSETS_TIER) -> Tier:
    """Block-onset tier for a results dir; empty if the onsets file is absent/unreadable."""
    path = Path(results_dir) / paths.BLOCK_WAV_ONSETS_MAT
    try:
        if not path.exists():
            return Tier(name, [])
        onsets = load_block_wav_onsets(path)
    except OSError:
        return Tier(name, [])
    return make_block_onsets_tier(onsets, name=name)
