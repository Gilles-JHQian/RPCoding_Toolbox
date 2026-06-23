"""A ViewBox whose left-drag selects a time span (Audacity-style) instead of panning.

Wheel still zooms (time); pan is via the scrollbar / zoom controls. Emits the dragged span in data
(time) coordinates; a near-zero span signals a plain click (clear selection).
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal


class SelectableViewBox(pg.ViewBox):
    region_selected = Signal(float, float)  # (x_down, x_now) in seconds; equal => click

    def mouseDragEvent(self, ev, axis=None):  # noqa: N802 - pyqtgraph override
        if ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()
            x0 = self.mapSceneToView(ev.buttonDownScenePos()).x()
            x1 = self.mapSceneToView(ev.scenePos()).x()
            self.region_selected.emit(float(x0), float(x1))
        else:
            super().mouseDragEvent(ev, axis)
