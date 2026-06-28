"""Spectrogram lane: memmapped log-spectrogram via ImageItem + magma + HistogramLUT."""

from __future__ import annotations

import gc

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QRectF

from rpcoding.core.audio.render.colormap import MAGMA_LUT
from rpcoding.core.audio.render.spectro import StftParams, frame_time_offset, slice_spectro
from rpcoding.gui.theme import Theme


class SpectrogramLane(QObject):
    def __init__(self, plot: pg.PlotItem, hist: pg.HistogramLUTItem, theme: Theme, parent=None):
        super().__init__(parent)
        self.plot = plot
        self._img = pg.ImageItem()
        self._img.setLookupTable(MAGMA_LUT)
        plot.addItem(self._img)

        self._hist = hist
        self._hist.setImageItem(self._img)
        try:
            self._hist.gradient.setColorMap(pg.ColorMap(np.linspace(0, 1, 256), MAGMA_LUT))
        except Exception:  # noqa: BLE001 - gradient styling is cosmetic
            pass

        self._mmap = None
        self._meta: dict | None = None
        self._t_off = 0.0  # seconds: STFT frame-centre alignment vs the waveform
        vb = plot.getViewBox()
        vb.setMenuEnabled(False)
        vb.enableAutoRange(x=False, y=False)
        self.apply_theme(theme)

    def set_source(self, spec_path, meta: dict) -> None:
        self.close_source()
        self._mmap = np.load(str(spec_path), mmap_mode="r")
        self._meta = meta
        # Align frames to the waveform. Prefer the stored offset; older caches (no t_offset/n_fft)
        # fall back to computing it from the default n_fft, since hop/fs are always present.
        n_fft = meta.get("n_fft", StftParams().n_fft)
        self._t_off = meta.get("t_offset", frame_time_offset(n_fft, meta["hop"], meta["fs"]))
        self.plot.setYRange(0, meta["n_rows"], padding=0)
        # Auto-scaled from the data percentiles, but with both bounds raised: the lower bound clips
        # more of the noise floor to black, the upper makes the loud parts less saturated overall.
        p2, p98 = meta["p2"], meta["p98"]
        rng = max(p98 - p2, 1e-6)
        self._hist.setLevels(p2 + 0.30 * rng, p98 + 0.25 * rng)

    def set_view(self, t0: float, t1: float, px: int) -> None:
        if self._mmap is None or self._meta is None:
            return
        img, x0, x1, nrows = slice_spectro(self._mmap, t0, t1, self._meta["dt"], px, self._t_off)
        self._img.setImage(img, autoLevels=False)
        self._img.setRect(QRectF(float(x0), 0.0, float(max(x1 - x0, 1e-9)), float(nrows)))

    def set_db_levels(self, lo: float, hi: float) -> None:
        self._hist.setLevels(float(lo), float(hi))

    def close_source(self) -> None:
        self._mmap = None
        self._meta = None
        gc.collect()  # release the memmap before any cache replace (Windows file-lock safe)

    def apply_theme(self, theme: Theme) -> None:
        self.plot.getViewBox().setBackgroundColor(theme.color("lane-bg"))
