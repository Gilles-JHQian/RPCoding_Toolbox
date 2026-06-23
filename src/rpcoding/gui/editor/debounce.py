"""Coalesce rapid visible-range changes into a single render request."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class RangeDebouncer(QObject):
    flushed = Signal(float, float, int)  # t0, t1, px_width

    def __init__(self, interval_ms: int = 40, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._emit)
        self._pending: tuple[float, float, int] | None = None

    def request(self, t0: float, t1: float, px: int) -> None:
        self._pending = (t0, t1, px)
        self._timer.start()

    def _emit(self) -> None:
        if self._pending is not None:
            self.flushed.emit(*self._pending)
