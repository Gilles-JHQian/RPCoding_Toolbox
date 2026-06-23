"""Qt-free callables run under ``run_in_thread`` to build/load the render caches.

Each returns a small handle (a pyramid object, or a path+meta dict), never the multi-hundred-MB
spectrogram array — the lane opens the memmap on the UI thread.
"""

from __future__ import annotations

from rpcoding.core.audio.render.cache import AudioRenderCache
from rpcoding.core.audio.render.pyramid import WaveformPyramid, build_pyramid_streaming
from rpcoding.core.audio.render.spectro import StftParams, build_log_spectrogram


def build_pyramid_job(wav_path, cache_root, content_key, progress=None) -> WaveformPyramid:
    cache = AudioRenderCache(cache_root)
    pyr = cache.load_pyramid(content_key)
    if pyr is None:
        pyr = build_pyramid_streaming(wav_path, progress=progress)
        cache.save_pyramid(content_key, pyr)
    return pyr


def build_spectrogram_job(
    wav_path, cache_root, content_key, params: StftParams | None = None, progress=None
) -> dict:
    params = params or StftParams()
    cache = AudioRenderCache(cache_root)
    sdir = cache.spectro_dir(content_key, params.key())
    spec_path = sdir / "spec.npy"
    meta = cache.read_meta(sdir)
    if meta is None or not spec_path.exists():
        sdir.mkdir(parents=True, exist_ok=True)
        meta = build_log_spectrogram(wav_path, spec_path, params, progress=progress)
        cache.write_meta(sdir, meta)
    return {"spec_path": str(spec_path), "meta": meta}
