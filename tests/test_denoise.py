"""Tests for noise-profile spectral denoising (core.audio.denoise)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("noisereduce")

from rpcoding.core.audio.denoise import denoise_allblocks, reduce_noise
from rpcoding.core.audio.io import read_wav, write_wav


def _noisy_signal(sr=8000, seconds=2.0, seed=0):
    """A sine in the first half + broadband noise everywhere -> a clear noise-only region after."""
    rng = np.random.default_rng(seed)
    n = int(sr * seconds)
    t = np.arange(n) / sr
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    tone[n // 2 :] = 0.0  # second half = no tone, just noise (the "silence" we'll measure)
    noise = 0.05 * rng.standard_normal(n)
    return (tone + noise).astype(np.float64), sr, n


def test_reduce_noise_lowers_the_noise_floor():
    sig, sr, n = _noisy_signal()
    noise_clip = sig[int(0.6 * sr) : int(0.9 * sr)]  # a noise-only span
    out = reduce_noise(sig, sr, noise_clip, prop_decrease=1.0)
    assert out.shape == sig.shape
    silent = slice(int(1.2 * sr), n)  # a region that was noise-only
    assert np.std(out[silent]) < np.std(sig[silent]) * 0.7  # noise floor clearly reduced


def test_reduce_noise_zero_strength_is_near_identity():
    sig, sr, _ = _noisy_signal()
    out = reduce_noise(sig, sr, sig[: int(0.3 * sr)], prop_decrease=0.0)
    assert np.std(out) > np.std(sig) * 0.9  # nothing removed at strength 0


def test_denoise_allblocks_writes_output_and_backs_up_raw(tmp_path):
    sig, sr, _ = _noisy_signal()
    allblocks = tmp_path / "allblocks.wav"
    original = tmp_path / "allblocks_original.wav"
    write_wav(allblocks, sig, sr)

    denoise_allblocks(allblocks, original, 0.6, 0.9, prop_decrease=1.0)

    assert original.exists()  # raw preserved
    raw, _ = read_wav(original)
    np.testing.assert_allclose(raw, sig, atol=1e-3)  # backup == the original raw signal
    out, _ = read_wav(allblocks)
    assert np.std(out[int(1.2 * sr) :]) < np.std(sig[int(1.2 * sr) :]) * 0.8  # allblocks denoised


def test_denoise_allblocks_does_not_compound_or_clobber_raw(tmp_path):
    sig, sr, _ = _noisy_signal()
    allblocks = tmp_path / "allblocks.wav"
    original = tmp_path / "allblocks_original.wav"
    write_wav(allblocks, sig, sr)

    denoise_allblocks(allblocks, original, 0.6, 0.9, prop_decrease=1.0)
    raw_after_first, _ = read_wav(original)
    # Re-applying reads from the preserved raw, so the backup is never overwritten with denoised.
    denoise_allblocks(allblocks, original, 0.6, 0.9, prop_decrease=0.5)
    raw_after_second, _ = read_wav(original)
    np.testing.assert_allclose(raw_after_first, raw_after_second, atol=1e-6)


def test_denoise_allblocks_rejects_too_short_profile(tmp_path):
    sig, sr, _ = _noisy_signal()
    allblocks = tmp_path / "allblocks.wav"
    write_wav(allblocks, sig, sr)
    with pytest.raises(ValueError, match="too short"):
        denoise_allblocks(allblocks, tmp_path / "orig.wav", 0.5, 0.5, prop_decrease=1.0)
