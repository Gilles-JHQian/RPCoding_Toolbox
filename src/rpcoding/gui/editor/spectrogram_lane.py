"""Spectrogram lane: memmapped log-spectrogram via ImageItem + magma + HistogramLUT."""

from __future__ import annotations

import gc

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QRectF

from rpcoding.core.audio.render.colormap import MAGMA_LUT
from rpcoding.core.audio.render.spectro import slice_spectro
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
        vb = plot.getViewBox()
        vb.setMenuEnabled(False)
        vb.enableAutoRange(x=False, y=False)
        self.apply_theme(theme)

    def set_source(self, spec_path, meta: dict) -> None:
        self.close_source()
        self._mmap = np.load(str(spec_path), mmap_mode="r")
        self._meta = meta
        self.plot.setYRange(0, meta["n_rows"], padding=0)
        self._hist.setLevels(meta["p2"], meta["p98"])

    def set_view(self, t0: float, t1: float, px: int) -> None:
        if self._mmap is None or self._meta is None:
            return
        img, x0, x1, nrows = slice_spectro(self._mmap, t0, t1, self._meta["dt"], px)
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
