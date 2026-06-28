"""Tests for WAV concatenation (combine_wavs.m port)."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from rpcoding.core.audio import concat
from rpcoding.core.audio.io import duration_seconds, read_wav
from rpcoding.core.matio import load_mat


def _write(path, data, fs):
    sf.write(str(path), np.asarray(data, dtype=np.float64), fs, subtype="PCM_16")


def test_block_number():
    assert concat.block_number("D134_Block_1_AllTrials.wav") == 1
    assert concat.block_number("block10.wav") == 10
    assert concat.block_number("notawav.txt") is None


def test_discover_orders_numerically(tmp_path):
    for name in [
        "D9_Block_2_AllTrials.wav",
        "D9_Block_10_AllTrials.wav",
        "D9_Block_1_AllTrials.wav",
        "readme.wav",  # no block number -> skipped
    ]:
        _write(tmp_path / name, np.zeros(10), 1000)
    blocks = concat.discover_block_wavs(tmp_path)
    assert [n for n, _ in blocks] == [1, 2, 10]


def test_concatenate_onsets_and_padding(tmp_path):
    fs, pad = 1000, 2.0
    b1, b2 = np.ones(5), np.full(3, 0.5)
    _write(tmp_path / "block1.wav", b1, fs)
    _write(tmp_path / "block2.wav", b2, fs)
    res = concat.concatenate_blocks(concat.discover_block_wavs(tmp_path), pad_seconds=pad)

    padlen = int(pad * fs)
    assert res.fs == fs
    assert len(res.audio) == len(b1) + padlen + len(b2) + padlen
    assert res.onsets[0, 0] == 1  # 1-based
    assert res.onsets[1, 0] == len(b1) + padlen + 1
    assert list(res.onsets[:, 1]) == [fs, fs]
    np.testing.assert_allclose(res.audio[:5], 1.0, atol=1e-3)
    np.testing.assert_allclose(res.audio[5 : 5 + padlen], 0.0, atol=1e-6)


def test_discover_aggregates_multiple_dirs(tmp_path):
    s1, s2 = tmp_path / "sess1", tmp_path / "sess2"
    s1.mkdir()
    s2.mkdir()
    _write(s1 / "D9_Block_1_AllTrials.wav", np.zeros(10), 1000)
    _write(s1 / "D9_Block_2_AllTrials.wav", np.zeros(10), 1000)
    _write(s2 / "D9_Block_3_AllTrials.wav", np.zeros(10), 1000)
    blocks = concat.discover_block_wavs([s1, s2])
    assert [n for n, _ in blocks] == [1, 2, 3]
    assert blocks[2][1].parent == s2


def test_discover_cross_session_dup_prefers_larger_then_later(tmp_path):
    s1, s2 = tmp_path / "sess1", tmp_path / "sess2"
    s1.mkdir()
    s2.mkdir()
    _write(s1 / "D9_Block_1_AllTrials.wav", np.zeros(4), 1000)  # smaller (aborted)
    _write(s2 / "D9_Block_1_AllTrials.wav", np.zeros(40), 1000)  # larger (complete) -> wins
    blocks = concat.discover_block_wavs([s1, s2])
    assert len(blocks) == 1
    assert blocks[0][1].parent == s2


def test_discover_in_dir_duplicate_still_raises(tmp_path):
    _write(tmp_path / "D9_Block_1_AllTrials.wav", np.zeros(4), 1000)
    _write(tmp_path / "block1.wav", np.zeros(4), 1000)  # same block number, one dir
    with pytest.raises(ValueError, match="Duplicate block 1"):
        concat.discover_block_wavs(tmp_path)


def test_fs_mismatch_raises(tmp_path):
    _write(tmp_path / "block1.wav", np.zeros(4), 1000)
    _write(tmp_path / "block2.wav", np.zeros(4), 2000)
    with pytest.raises(ValueError, match="mismatch"):
        concat.concatenate_blocks(concat.discover_block_wavs(tmp_path))


def test_missing_block_leaves_zero_row(tmp_path):
    _write(tmp_path / "block1.wav", np.ones(4), 500)
    _write(tmp_path / "block3.wav", np.ones(4), 500)
    res = concat.concatenate_blocks(concat.discover_block_wavs(tmp_path))
    assert res.onsets.shape == (3, 2)
    assert list(res.onsets[1]) == [0.0, 0.0]  # block 2 missing
    assert res.onsets[2, 0] == 4 + int(10 * 500) + 1  # block 3 starts after block 1 + 10s pad


def test_combine_wavs_reports_progress(tmp_path):
    fs = 500
    for n in (1, 2, 3):
        _write(tmp_path / f"block{n}.wav", np.ones(4), fs)
    ticks: list = []
    concat.combine_wavs(
        tmp_path,
        tmp_path / "allblocks.wav",
        tmp_path / "onsets.mat",
        report=lambda f, m: ticks.append((f, m)),
    )
    # one read tick per block (mapped into the first 80%), then write/finish ending at 1.0.
    assert any("block 1" in m.lower() for _f, m in ticks)
    assert any("block 3" in m.lower() for _f, m in ticks)
    fractions = [f for f, _m in ticks if f is not None]
    assert fractions == sorted(fractions)  # monotonic, never goes backwards
    assert ticks[-1][0] == 1.0


def test_combine_wavs_writes_outputs(tmp_path):
    fs = 800
    _write(tmp_path / "block1.wav", np.ones(6), fs)
    out_wav = tmp_path / "allblocks.wav"
    out_mat = tmp_path / "block_wav_onsets.mat"
    res = concat.combine_wavs(tmp_path, out_wav, out_mat)

    assert out_wav.exists() and out_mat.exists()
    assert res.onsets[0, 0] == 1
    assert abs(duration_seconds(out_wav) - (6 + 10 * fs) / fs) < 1e-3
    # load without simplify so the (1, 2) numeric matrix keeps its 2-D shape
    onsets = load_mat(out_mat, simplify=False)["block_wav_onsets"]
    assert onsets[0, 0] == 1 and onsets[0, 1] == fs


def test_read_wav_rejects_stereo(tmp_path):
    sf.write(str(tmp_path / "s.wav"), np.zeros((10, 2)), 1000, subtype="PCM_16")
    with pytest.raises(ValueError, match="mono"):
        read_wav(tmp_path / "s.wav")
