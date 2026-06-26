"""Noise-profile spectral noise reduction (Audacity-style), built on ``noisereduce``.

Mirrors Audacity's two-step flow: the user selects a noise-only span ("Get Noise Profile"), then the
whole signal is denoised against that profile at a chosen strength ("Noise Reduction"). The profile
is a clip of the signal; ``prop_decrease`` (0..1) is the reduction strength.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rpcoding.core.audio.io import read_wav, write_wav


def _exists(p: Path) -> bool:
    """``p.exists()`` that treats an un-stat-able cloud placeholder (OSError) as absent."""
    try:
        return p.exists()
    except OSError:
        return False


def reduce_noise(
    signal: np.ndarray, sr: int, noise_clip: np.ndarray, prop_decrease: float = 1.0
) -> np.ndarray:
    """Spectrally subtract the noise estimated from ``noise_clip`` out of ``signal``.

    ``prop_decrease`` in ``[0, 1]`` is the strength (how much of the estimated noise to remove);
    0 leaves the signal unchanged, 1 removes the full estimate. Returns float64, same length.
    """
    import noisereduce as nr

    reduced = nr.reduce_noise(
        y=np.asarray(signal, dtype=np.float32),
        sr=int(sr),
        y_noise=np.asarray(noise_clip, dtype=np.float32),
        stationary=True,  # profile-based estimate, like Audacity's noise profile
        prop_decrease=float(prop_decrease),
    )
    return np.asarray(reduced, dtype=np.float64)


def denoise_allblocks(
    allblocks_wav: Path | str,
    original_wav: Path | str,
    noise_start: float,
    noise_end: float,
    prop_decrease: float,
) -> tuple[int, int]:
    """Denoise ``allblocks_wav`` in place using ``[noise_start, noise_end]`` (seconds) as profile.

    Always denoises from the *raw* signal — preserved once as ``original_wav`` — so re-applying with
    a different strength never compounds. Returns ``(sample_rate, n_samples)``.
    """
    allblocks_wav = Path(allblocks_wav)
    original_wav = Path(original_wav)
    raw_path = original_wav if _exists(original_wav) else allblocks_wav
    signal, sr = read_wav(raw_path)

    n0 = max(0, min(int(round(noise_start * sr)), len(signal)))
    n1 = max(0, min(int(round(noise_end * sr)), len(signal)))
    if n1 - n0 < 2:
        raise ValueError("noise-profile selection is too short — select a longer noise-only span")

    reduced = reduce_noise(signal, sr, signal[n0:n1], prop_decrease)
    if not _exists(original_wav):
        write_wav(original_wav, signal, sr)  # preserve the raw audio once
    write_wav(allblocks_wav, reduced, sr)
    return sr, len(signal)
