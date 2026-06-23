"""On-disk cache for the waveform pyramid and log-spectrogram (keyed by content hash + params).

Layout under ``<results>/.rpcoding/cache/``::

    <content_key>/
        pyramid/waveform_pyramid.npz
        spectro/<stft_key>/spec.npy + meta.json   (meta.json written last = build-complete sentinel)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rpcoding.core.audio.render.hashing import content_hash
from rpcoding.core.audio.render.pyramid import (
    BASE_DECIM,
    LEVEL_FACTOR,
    PYRAMID_VERSION,
    WaveformPyramid,
)


def _atomic_replace(tmp: Path, dst: Path) -> None:
    os.replace(tmp, dst)


@dataclass
class AudioRenderCache:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    def content_key(self, wav_path: Path | str) -> str:
        return f"{content_hash(wav_path)}_pv{PYRAMID_VERSION}_d{BASE_DECIM}_f{LEVEL_FACTOR}"

    def dir_for(self, content_key: str) -> Path:
        return self.root / content_key

    def pyramid_path(self, content_key: str) -> Path:
        return self.dir_for(content_key) / "pyramid" / "waveform_pyramid.npz"

    def spectro_dir(self, content_key: str, stft_key: str) -> Path:
        return self.dir_for(content_key) / "spectro" / stft_key

    # ---- waveform pyramid ----
    def save_pyramid(self, content_key: str, pyr: WaveformPyramid) -> Path:
        path = self.pyramid_path(content_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"level_{i}": lv for i, lv in enumerate(pyr.levels)}
        arrays["decims"] = np.asarray(pyr.decims, dtype=np.int64)
        arrays["meta"] = np.asarray(
            [pyr.n_samples, pyr.fs, len(pyr.levels), PYRAMID_VERSION], dtype=np.int64
        )
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as fh:
            np.savez(fh, **arrays)
        _atomic_replace(tmp, path)
        return path

    def load_pyramid(self, content_key: str) -> WaveformPyramid | None:
        path = self.pyramid_path(content_key)
        if not path.exists():
            return None
        with np.load(path) as z:
            meta = z["meta"]
            if int(meta[3]) != PYRAMID_VERSION:
                return None
            n_levels = int(meta[2])
            levels = [z[f"level_{i}"].copy() for i in range(n_levels)]
            decims = [int(d) for d in z["decims"]]
            n_samples, fs = int(meta[0]), int(meta[1])
        return WaveformPyramid(levels=levels, decims=decims, n_samples=n_samples, fs=fs)

    # ---- spectrogram meta (the spec.npy memmap is opened directly by the caller) ----
    def write_meta(self, spectro_dir: Path, meta: dict) -> None:
        spectro_dir.mkdir(parents=True, exist_ok=True)
        tmp = spectro_dir / "meta.json.tmp"
        tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")
        _atomic_replace(tmp, spectro_dir / "meta.json")

    def read_meta(self, spectro_dir: Path) -> dict | None:
        path = spectro_dir / "meta.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
