"""Placeholder X-linked label lane — the extension point for the label-tracks branch."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QObject

from rpcoding.gui.theme import Theme

LABEL_LANE_HEIGHT = 40


class LabelLane(QObject):
    def __init__(self, plot: pg.PlotItem, name: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.name = name
        self._theme = theme
        vb = plot.getViewBox()
        vb.setMouseEnabled(x=True, y=False)
        vb.setMenuEnabled(False)
        vb.enableAutoRange(x=False, y=False)
        plot.setYRange(0.0, 1.0, padding=0)
        self.apply_theme(theme)

    def set_view(self, t0: float, t1: float, px: int) -> None:
        # Intervals are drawn in the label-tracks branch; nothing to reslice yet.
        return

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.plot.getViewBox().setBackgroundColor(theme.color("panel"))
