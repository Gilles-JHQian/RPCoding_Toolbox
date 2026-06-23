"""Tests for content hashing and the audio render cache (pure numpy)."""

from __future__ import annotations

import numpy as np

from rpcoding.core.audio.render.cache import AudioRenderCache
from rpcoding.core.audio.render.hashing import content_hash
from rpcoding.core.audio.render.pyramid import build_pyramid


def test_content_hash_stable_and_sensitive(tmp_path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"x" * 100)
    h1 = content_hash(p)
    assert h1 == content_hash(p) and len(h1) == 16
    p.write_bytes(b"y" * 100)
    assert content_hash(p) != h1


def test_pyramid_save_load_roundtrip(tmp_path):
    x = np.random.default_rng(0).standard_normal(300_000).astype(np.float32)
    p = build_pyramid(x, 1234)
    cache = AudioRenderCache(tmp_path / "cache")
    cache.save_pyramid("k", p)

    q = cache.load_pyramid("k")
    assert q is not None
    assert q.n_samples == p.n_samples and q.fs == 1234
    assert q.decims == p.decims and len(q.levels) == len(p.levels)
    np.testing.assert_array_equal(q.levels[0], p.levels[0])
    assert not list(cache.pyramid_path("k").parent.glob("*.tmp"))  # atomic, no leftovers


def test_load_missing_returns_none(tmp_path):
    assert AudioRenderCache(tmp_path).load_pyramid("nope") is None


def test_meta_roundtrip(tmp_path):
    cache = AudioRenderCache(tmp_path)
    d = cache.spectro_dir("ck", "sk")
    assert cache.read_meta(d) is None
    cache.write_meta(d, {"shape": [256, 100], "dt": 0.01})
    assert cache.read_meta(d)["shape"] == [256, 100]


def test_content_key_format(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"z" * 1000)
    assert "_pv1_d256_f4" in AudioRenderCache(tmp_path).content_key(p)
