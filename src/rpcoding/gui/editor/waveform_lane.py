"""Waveform lane: min/max envelope from the LOD pyramid (raw samples when zoomed past level 0)."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor

from rpcoding.core.audio.render.pyramid import (
    WaveformPyramid,
    _level0_from_samples,
    pick_level,
    slice_level,
)
from rpcoding.gui.theme import Theme


class WaveformLane(QObject):
    def __init__(self, plot: pg.PlotItem, theme: Theme, parent=None):
        super().__init__(parent)
        self.plot = plot
        self._pyr: WaveformPyramid | None = None
        self._fs = 1
        self._wav: str | None = None
        self._gain = 1.0

        self._top = pg.PlotCurveItem()
        self._bot = pg.PlotCurveItem()
        self._fill = pg.FillBetweenItem(self._top, self._bot)
        plot.addItem(self._fill)
        plot.addItem(self._top)
        plot.addItem(self._bot)

        vb = plot.getViewBox()
        vb.setMenuEnabled(False)
        vb.enableAutoRange(x=False, y=False)
        plot.setYRange(-1.0, 1.0, padding=0)
        self.apply_theme(theme)

    def set_source(self, pyr: WaveformPyramid, wav_path=None) -> None:
        self._pyr = pyr
        self._fs = pyr.fs or 1
        self._wav = str(wav_path) if wav_path else None

    def set_view(self, t0: float, t1: float, px: int) -> None:
        if self._pyr is None:
            return
        x0 = max(int(t0 * self._fs), 0)
        x1 = min(int(t1 * self._fs), self._pyr.n_samples)
        if x1 <= x0:
            return
        lvl = pick_level(self._pyr.decims, x0, x1, px)
        if lvl < 0 and self._wav is not None:
            import soundfile as sf

            data, _ = sf.read(self._wav, start=x0, frames=x1 - x0, dtype="float32", always_2d=False)
            if data.ndim == 2:
                data = data[:, 0]
            if len(data) > 2 * px:
                # on-the-fly min/max decimation so we never plot more than ~2*px points
                decim = max(len(data) // px, 1)
                mn, mx = _level0_from_samples(data, decim)
                centers = (np.arange(len(mn), dtype=np.float64) * decim + decim / 2 + x0) / self._fs
                self._top.setData(centers, mx.astype(np.float64))
                self._bot.setData(centers, mn.astype(np.float64))
            else:
                xs = np.arange(x0, x0 + len(data), dtype=np.float64) / self._fs
                self._top.setData(xs, data)
                self._bot.setData(xs, data)
            return
        if lvl < 0:
            lvl = 0
        centers, mn, mx = slice_level(self._pyr, lvl, x0, x1)
        xs = centers / self._fs
        self._top.setData(xs, mx.astype(np.float64))
        self._bot.setData(xs, mn.astype(np.float64))

    def set_gain(self, gain: float) -> None:
        self._gain = max(float(gain), 1e-3)
        self.plot.setYRange(-1.0 / self._gain, 1.0 / self._gain, padding=0)

    def apply_theme(self, theme: Theme) -> None:
        stroke = theme.color("wave-stroke")
        pen = pg.mkPen(stroke, width=1)
        self._top.setPen(pen)
        self._bot.setPen(pen)
        fill = QColor(stroke)
        fill.setAlpha(80)
        self._fill.setBrush(pg.mkBrush(fill))
        self.plot.getViewBox().setBackgroundColor(theme.color("lane-bg"))
