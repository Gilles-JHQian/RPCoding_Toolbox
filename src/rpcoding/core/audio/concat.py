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
from rpcoding.core.matio import load_mat, save_mat
from rpcoding.core.progress import Reporter, noop, sub

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


# Per-trial wavs (``D24_Block_1_Trial_10.wav``) and practice files live alongside the block-level
# ``*_Block_<n>_AllTrials.wav`` in some sessions; they must not be mistaken for block wavs.
_PER_TRIAL_RE = re.compile(r"_Trial_\d+", re.IGNORECASE)


def discover_block_wavs(directory: Path | str) -> list[tuple[int, Path]]:
    """Find block wavs in ``directory`` -> ``[(block_number, path), ...]`` sorted by number.

    Matches ``*_Block_<n>_*.wav`` (e.g. ``D134_Block_1_AllTrials.wav``) and legacy ``block<n>.wav``,
    skipping per-trial (``*_Trial_<m>*``) and practice files. Raises on a duplicate block number.
    """
    directory = Path(directory)
    found: dict[int, Path] = {}
    for p in sorted(directory.glob("*.wav")):
        if _PER_TRIAL_RE.search(p.name) or "pract" in p.name.lower():
            continue
        n = block_number(p.name)
        if n is None:
            continue
        if n in found:
            raise ValueError(f"Duplicate block {n}: {found[n].name} and {p.name}")
        found[n] = p
    return sorted(found.items())


def concatenate_blocks(
    blocks: list[tuple[int, Path]],
    pad_seconds: float = DEFAULT_PAD_SECONDS,
    report: Reporter | None = None,
) -> ConcatResult:
    """Concatenate ``(block_number, path)`` wavs with inter-block silence (combine_wavs.m)."""
    if not blocks:
        raise ValueError("No block wavs to concatenate")
    r = report or noop

    blocks = sorted(blocks)
    max_block = max(n for n, _ in blocks)
    onsets = np.zeros((max_block, 2), dtype=np.float64)

    parts: list[np.ndarray] = []
    fs0: int | None = None
    length = 0
    total = len(blocks)
    for i, (n, path) in enumerate(blocks):
        r(i / total, f"Reading block {n} ({i + 1}/{total})…")
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
    r(1.0, "Concatenating blocks…")
    return ConcatResult(audio=np.concatenate(parts), fs=fs0, onsets=onsets)


def save_block_wav_onsets(path: Path | str, onsets: np.ndarray) -> None:
    """Write ``block_wav_onsets.mat`` (variable ``block_wav_onsets``)."""
    save_mat(path, {"block_wav_onsets": np.asarray(onsets, dtype=np.float64)})


def load_block_wav_onsets(path: Path | str) -> np.ndarray:
    """Read ``block_wav_onsets.mat`` back to the ``(max_block, 2)`` [start sample, fs] array.

    ``np.atleast_2d`` restores the row shape when a single-block file is squeezed to ``(2,)``.
    """
    arr = np.asarray(load_mat(path)["block_wav_onsets"], dtype=np.float64)
    return np.atleast_2d(arr)


def combine_wavs(
    block_dir: Path | str,
    out_wav: Path | str,
    out_onsets_mat: Path | str,
    pad_seconds: float = DEFAULT_PAD_SECONDS,
    report: Reporter | None = None,
) -> ConcatResult:
    """Discover blocks in ``block_dir``, concatenate, write allblocks.wav + onsets.mat."""
    r = report or noop
    blocks = discover_block_wavs(block_dir)
    if not blocks:
        raise FileNotFoundError(f"No block wavs found in {block_dir}")
    # Reading the per-block wavs is the bulk of the work -> give it 80% of the bar.
    result = concatenate_blocks(blocks, pad_seconds=pad_seconds, report=sub(report, 0.0, 0.8))
    r(0.85, "Writing allblocks.wav…")
    write_wav(out_wav, result.audio, result.fs)
    r(0.96, "Writing block onsets…")
    save_block_wav_onsets(out_onsets_mat, result.onsets)
    r(1.0, "Concatenation complete")
    return result
