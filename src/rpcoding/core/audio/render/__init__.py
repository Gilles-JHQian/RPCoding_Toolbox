"""Qt-free audio-render numerics: content hashing, waveform LOD pyramid, log-spectrogram, cache.

The GUI editor (``rpcoding.gui.editor``) builds on these; everything here is pure
numpy/scipy/soundfile so it stays under the headless-core guard and is unit-testable without Qt.
"""

from rpcoding.core.audio.render.cache import AudioRenderCache
from rpcoding.core.audio.render.colormap import MAGMA_LUT, MAGMA_STOPS
from rpcoding.core.audio.render.hashing import content_hash
from rpcoding.core.audio.render.pyramid import (
    BASE_DECIM,
    LEVEL_FACTOR,
    PYRAMID_VERSION,
    WaveformPyramid,
    build_pyramid,
    build_pyramid_streaming,
    pick_level,
    slice_level,
)
from rpcoding.core.audio.render.spectro import (
    StftParams,
    build_log_spectrogram,
    db_magnitude,
    n_frames,
    pool_columns_max,
    slice_spectro,
)

__all__ = [
    "AudioRenderCache",
    "MAGMA_LUT",
    "MAGMA_STOPS",
    "content_hash",
    "BASE_DECIM",
    "LEVEL_FACTOR",
    "PYRAMID_VERSION",
    "WaveformPyramid",
    "build_pyramid",
    "build_pyramid_streaming",
    "pick_level",
    "slice_level",
    "StftParams",
    "build_log_spectrogram",
    "db_magnitude",
    "n_frames",
    "pool_columns_max",
    "slice_spectro",
]
