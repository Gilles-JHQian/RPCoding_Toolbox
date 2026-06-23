"""Selection model: a single (start, end) time span shared across lanes."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class SelectionModel(QObject):
    changed = Signal(object)  # (start, end) | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._span: tuple[float, float] | None = None

    def span(self) -> tuple[float, float] | None:
        return self._span

    def set_span(self, span: tuple[float, float] | None) -> None:
        if span is not None:
            a, b = span
            span = (min(a, b), max(a, b))
        if span != self._span:
            self._span = span
            self.changed.emit(span)

    def clear(self) -> None:
        self.set_span(None)
