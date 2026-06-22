r"""Port of ``combine_wavs.m``: concatenate per-block WAVs into ``allblocks.wav``.

Blocks are concatenated in block-number order, each followed by 10 s of silence (after the last
block too, matching the MATLAB). ``block_wav_onsets`` records, per block, the **1-based** sample
index where the block begins in the concatenated signal and the sample rate -- exactly as
``combine_wavs.m`` does (indexed by block number, so a missing block leaves a zero row).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rpcoding.core.audio.io import read_wav, write_wav
from rpcoding.core.matio import save_mat

DEFAULT_PAD_SECONDS = 10.0

_BLOCK_PATTERNS = (
    re.compile(r"_Block_(\d+)_", re.IGNORECASE),
    re.compile(r"^block(\d+)\.wav$", re.IGNORECASE),
)


@dataclass
class ConcatResult:
    """Result of concatenation: the signal, its sample rate, and per-block onsets."""

    audio: np.ndarray
    fs: int
    onsets: np.ndarray  # (max_block, 2): [1-based start sample, fs] per block number


def block_number(filename: str) -> int | None:
    """Extract the block number from a wav filename, or None if it doesn't match."""
    for pat in _BLOCK_PATTERNS:
        m = pat.search(filename)
        if m:
            return int(m.group(1))
    return None


def discover_block_wavs(directory: Path | str) -> list[tuple[int, Path]]:
    """Find block wavs in ``directory`` -> ``[(block_number, path), ...]`` sorted by number.

    Matches ``*_Block_<n>_*.wav`` (e.g. ``D134_Block_1_AllTrials.wav``) and legacy
    ``block<n>.wav``. Raises if two files claim the same block number.
    """
    directory = Path(directory)
    found: dict[int, Path] = {}
    for p in sorted(directory.glob("*.wav")):
        n = block_number(p.name)
        if n is None:
            continue
        if n in found:
            raise ValueError(f"Duplicate block {n}: {found[n].name} and {p.name}")
        found[n] = p
    return sorted(found.items())


def concatenate_blocks(
    blocks: list[tuple[int, Path]], pad_seconds: float = DEFAULT_PAD_SECONDS
) -> ConcatResult:
    """Concatenate ``(block_number, path)`` wavs with inter-block silence (combine_wavs.m)."""
    if not blocks:
        raise ValueError("No block wavs to concatenate")

    blocks = sorted(blocks)
    max_block = max(n for n, _ in blocks)
    onsets = np.zeros((max_block, 2), dtype=np.float64)

    parts: list[np.ndarray] = []
    fs0: int | None = None
    length = 0
    for n, path in blocks:
        data, fs = read_wav(path)
        if fs0 is None:
            fs0 = fs
        elif fs != fs0:
            raise ValueError(f"Sample-rate mismatch: block {n} is {fs} Hz, expected {fs0} Hz")
        onsets[n - 1, 0] = length + 1  # 1-based start sample, recorded before appending
        onsets[n - 1, 1] = fs
        pad = np.zeros(int(round(pad_seconds * fs)), dtype=np.float64)
        parts.append(data)
        parts.append(pad)
        length += len(data) + len(pad)

    assert fs0 is not None
    return ConcatResult(audio=np.concatenate(parts), fs=fs0, onsets=onsets)


def save_block_wav_onsets(path: Path | str, onsets: np.ndarray) -> None:
    """Write ``block_wav_onsets.mat`` (variable ``block_wav_onsets``)."""
    save_mat(path, {"block_wav_onsets": np.asarray(onsets, dtype=np.float64)})


def combine_wavs(
    block_dir: Path | str,
    out_wav: Path | str,
    out_onsets_mat: Path | str,
    pad_seconds: float = DEFAULT_PAD_SECONDS,
) -> ConcatResult:
    """Discover blocks in ``block_dir``, concatenate, write allblocks.wav + onsets.mat."""
    blocks = discover_block_wavs(block_dir)
    if not blocks:
        raise FileNotFoundError(f"No block wavs found in {block_dir}")
    result = concatenate_blocks(blocks, pad_seconds=pad_seconds)
    write_wav(out_wav, result.audio, result.fs)
    save_block_wav_onsets(out_onsets_mat, result.onsets)
    return result
