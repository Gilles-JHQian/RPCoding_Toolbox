"""A lane ViewBox with uniform time-axis interaction across every track.

Left-drag selects a time span; Ctrl+wheel zooms the time axis about the cursor; Shift+wheel pans.
Plain wheel does nothing. The same viewbox is used on the waveform, spectrogram and every label
lane, so the gestures work no matter which track the pointer is over; it emits the resulting intent
and the editor applies it to the shared (x-linked) time axis.
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal


class InteractiveViewBox(pg.ViewBox):
    region_selected = Signal(float, float)  # (x_down, x_now) seconds; equal => click
    zoom_requested = Signal(float, float)  # (centre_seconds, factor)  factor<1 zooms in
    pan_requested = Signal(float)  # fraction of the view width to shift (+ = later in time)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseEnabled(x=False, y=False)  # gestures are handled here, not by the base box

    def mouseDragEvent(self, ev, axis=None):  # noqa: N802 - pyqtgraph override
        if ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()
            x0 = self.mapSceneToView(ev.buttonDownScenePos()).x()
            x1 = self.mapSceneToView(ev.scenePos()).x()
            self.region_selected.emit(float(x0), float(x1))
        else:
            super().mouseDragEvent(ev, axis)

    def wheelEvent(self, ev, axis=None):  # noqa: N802 - pyqtgraph override
        delta = ev.delta()
        if delta == 0:
            ev.ignore()
            return
        mods = ev.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            centre = self.mapSceneToView(ev.scenePos()).x()
            self.zoom_requested.emit(float(centre), 0.8 if delta > 0 else 1.25)
            ev.accept()
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            self.pan_requested.emit(-0.18 if delta > 0 else 0.18)
            ev.accept()
        else:
            ev.ignore()  # plain wheel is a no-op (Ctrl = zoom, Shift = pan)
