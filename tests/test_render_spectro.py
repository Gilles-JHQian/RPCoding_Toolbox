"""Tests for the log-spectrogram math + colormap (pure numpy; build round-trip gated)."""

from __future__ import annotations

import numpy as np
import pytest

from rpcoding.core.audio.render.colormap import MAGMA_LUT
from rpcoding.core.audio.render.spectro import (
    StftParams,
    _interp_to_log,
    _log_interp_weights,
    db_magnitude,
    frame_time_offset,
    n_frames,
    pool_columns_max,
    slice_spectro,
)


def test_magma_lut():
    assert MAGMA_LUT.shape == (256, 3) and MAGMA_LUT.dtype == np.uint8
    assert tuple(MAGMA_LUT[0]) == (0, 0, 4)
    assert tuple(MAGMA_LUT[-1]) == (252, 253, 191)


def test_db_conversion():
    assert abs(db_magnitude(np.array([1.0]))[0]) < 1e-4  # |1| -> 0 dB
    floorval = db_magnitude(np.array([0.0]))[0]
    assert np.isfinite(floorval) and floorval < -150
    assert db_magnitude(np.array([1.0])).dtype == np.float32


def test_n_frames_matches_real_file():
    assert n_frames(135_000_000, 2048, 512) == 263668
    assert n_frames(100, 2048, 512) == 0


def test_pool_identity_and_shape():
    b = np.arange(20, dtype=np.float32).reshape(2, 10)
    assert pool_columns_max(b, 20) is b
    assert pool_columns_max(b, 5).shape == (2, 5)


def test_pool_exact_multiple_takes_max():
    b = np.arange(2 * 8, dtype=np.float32).reshape(2, 8)
    p = pool_columns_max(b, 4)  # segments of width 2
    assert p[0, 0] == 1 and p[0, 1] == 3 and p[0, 3] == 7


def test_pool_preserves_peak_under_extreme_decimation():
    b = np.zeros((4, 1_000_000), dtype=np.float32)
    b[1, 500_000] = 9.0
    assert pool_columns_max(b, 1000).max() == 9.0


def test_interp_to_log_grid():
    lin_f = np.linspace(0, 22050, 1025)
    log_f = np.geomspace(80, 8000, 256)
    idx, frac = _log_interp_weights(lin_f, log_f)
    assert idx.min() >= 0 and idx.max() <= 1023
    out = _interp_to_log(np.full((1025, 5), 3.0, np.float32), idx, frac)
    assert out.shape == (256, 5)
    np.testing.assert_allclose(out, 3.0, atol=1e-5)


def test_slice_spectro_window_and_rows():
    mm = np.zeros((256, 1000), dtype=np.float32)
    img, x0, x1, nrows = slice_spectro(mm, 0.0, 1.0, 0.01, 500)
    assert nrows == 256 and img.shape[0] == 256
    assert x0 <= 0.0 and x1 >= 1.0


def test_frame_time_offset_formula():
    # frame c is centred on sample c*hop + n_fft/2 -> shift = (n_fft - hop) / (2*fs)
    assert frame_time_offset(2048, 512, 48000) == pytest.approx((2048 - 512) / (2 * 48000))
    assert frame_time_offset(1024, 256, 16000) == pytest.approx(0.024)  # 768 / 32000


def test_slice_spectro_offset_aligns_frames_to_waveform():
    mm = np.zeros((4, 100), dtype=np.float32)
    mm[0] = np.arange(100)  # encode each column's index in row 0
    dt = 0.01
    img0, x0a, _x1a, _ = slice_spectro(mm, 0.30, 0.40, dt, 1000)  # no offset (default)
    img1, x0b, _x1b, _ = slice_spectro(mm, 0.30, 0.40, dt, 1000, t_offset=0.05)
    # Same screen window, but the offset pulls in 5 earlier frames (0.05 s / 0.01 dt) -> the whole
    # spectrogram shifts right so a frame lands under the matching waveform sample.
    assert x0a == pytest.approx(0.30) and x0b == pytest.approx(0.30)
    assert img0[0, 0] == 30 and img1[0, 0] == 25


def test_build_log_spectrogram_roundtrip(tmp_path):
    pytest.importorskip("scipy")
    sf = pytest.importorskip("soundfile")  # noqa: F841 - ensures libsndfile is available
    from rpcoding.core.audio.io import read_wav, write_wav
    from rpcoding.core.audio.render.pyramid import build_pyramid, build_pyramid_streaming
    from rpcoding.core.audio.render.spectro import build_log_spectrogram

    fs = 16000
    t = np.arange(fs * 2) / fs
    x = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav = tmp_path / "tone.wav"
    write_wav(wav, x, fs)

    out = tmp_path / "spec.npy"
    meta = build_log_spectrogram(wav, out, StftParams(n_fft=1024, hop=256))
    arr = np.load(out, mmap_mode="r")
    assert arr.shape == (256, meta["shape"][1]) and arr.dtype == np.float32
    assert meta["n_fft"] == 1024
    assert meta["t_offset"] == pytest.approx((1024 - 256) / (2 * fs))  # frame-centre alignment

    log_f = np.geomspace(80, 8000, 256)
    peak_row = int(np.argmax(np.asarray(arr).mean(axis=1)))
    assert abs(log_f[peak_row] - 440) / 440 < 0.2  # dominant energy near 440 Hz

    # streaming pyramid matches the in-RAM pyramid built from the same (read-back) samples
    xr, _ = read_wav(wav)
    p_stream = build_pyramid_streaming(wav)
    p_ram = build_pyramid(xr, fs)
    assert p_stream.decims == p_ram.decims
    np.testing.assert_allclose(p_stream.levels[0], p_ram.levels[0], atol=1e-4)
