"""WAV read/write helpers (mono, float64) built on soundfile."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    """Read a mono WAV as float64 in [-1, 1]. Returns ``(samples_1d, sample_rate)``."""
    data, fs = sf.read(str(path), dtype="float64", always_2d=False)
    if data.ndim == 2:
        if data.shape[1] == 1:
            data = data[:, 0]
        else:
            raise ValueError(f"{path}: expected mono audio, got {data.shape[1]} channels")
    return np.ascontiguousarray(data), int(fs)


def write_wav(path: Path | str, data: np.ndarray, fs: int) -> None:
    """Write a 1-D float array as a 16-bit PCM WAV (matching MATLAB audiowrite defaults)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(data), int(fs), subtype="PCM_16")


def duration_seconds(path: Path | str) -> float:
    """Duration of a WAV in seconds (without loading the samples)."""
    info = sf.info(str(path))
    return info.frames / info.samplerate
