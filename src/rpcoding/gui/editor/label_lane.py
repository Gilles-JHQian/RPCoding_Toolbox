"""Label lane: renders a Tier as draggable regions + text; create / edit / select / navigate."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from rpcoding.core.labels import Interval, Tier
from rpcoding.gui.theme import Theme

LABEL_LANE_HEIGHT = 40
_UNSEL = "#3a4250"


class _LabelItem:
    __slots__ = ("region", "text", "interval")

    def __init__(self, region, text, interval: Interval):
        self.region = region
        self.text = text
        self.interval = interval


class LabelLane(QObject):
    tier_changed = Signal()
    label_selected = Signal(object)  # Interval | None

    def __init__(
        self, plot: pg.PlotItem, name: str, theme: Theme, editable: bool = False, parent=None
    ):
        super().__init__(parent)
        self.plot = plot
        self.name = name
        self.editable = editable
        self._theme = theme
        self._items: list[_LabelItem] = []
        self._active = -1

        vb = plot.getViewBox()
        vb.setMenuEnabled(False)
        vb.enableAutoRange(x=False, y=False)
        plot.setYRange(0.0, 1.0, padding=0)
        self.apply_theme(theme)

    # ---- tier I/O ----
    def set_tier(self, tier: Tier) -> None:
        self.clear()
        for iv in tier.intervals:
            self._add_item(iv)

    def get_tier(self) -> Tier:
        intervals = sorted((it.interval for it in self._items), key=lambda i: i.start)
        return Tier(self.name, list(intervals))

    def intervals(self) -> list[Interval]:
        return [it.interval for it in self._items]

    # ---- editing ----
    def create(self, start: float, end: float, label: str = "") -> Interval:
        iv = Interval(min(start, end), max(start, end), label)
        self._add_item(iv)
        self.tier_changed.emit()
        self.select(len(self._items) - 1)
        return iv

    def delete_active(self) -> None:
        if not (0 <= self._active < len(self._items)):
            return
        item = self._items.pop(self._active)
        self.plot.removeItem(item.region)
        self.plot.removeItem(item.text)
        self._active = min(self._active, len(self._items) - 1)
        self.tier_changed.emit()
        self._emit_active()

    def rename_active(self, label: str) -> None:
        if not (0 <= self._active < len(self._items)):
            return
        item = self._items[self._active]
        item.interval = Interval(item.interval.start, item.interval.end, label)
        item.text.setText(label)
        self.tier_changed.emit()

    # ---- selection / navigation ----
    def select(self, index: int) -> None:
        self._active = index if 0 <= index < len(self._items) else -1
        for i, it in enumerate(self._items):
            self._style_region(it.region, selected=(i == self._active))
        self._emit_active()

    def active_interval(self) -> Interval | None:
        return self._items[self._active].interval if 0 <= self._active < len(self._items) else None

    def select_step(self, step: int) -> Interval | None:
        """Select next (step>0) / previous (step<0) label by start time; wraps."""
        if not self._items:
            return None
        order = sorted(range(len(self._items)), key=lambda i: self._items[i].interval.start)
        if self._active < 0:
            new = order[0] if step > 0 else order[-1]
        else:
            pos = order.index(self._active)
            new = order[(pos + (1 if step > 0 else -1)) % len(order)]
        self.select(new)
        return self._items[new].interval

    def clear(self) -> None:
        for it in self._items:
            self.plot.removeItem(it.region)
            self.plot.removeItem(it.text)
        self._items = []
        self._active = -1

    def set_view(self, t0: float, t1: float, px: int) -> None:
        # Regions live in data coordinates; pyqtgraph repositions them on pan/zoom automatically.
        return

    # ---- internals ----
    def _add_item(self, iv: Interval) -> _LabelItem:
        region = pg.LinearRegionItem(values=[iv.start, iv.end], movable=self.editable)
        region.setZValue(10)
        text = pg.TextItem(iv.label, anchor=(0.5, 0.5), color=self._theme.color("text-pri"))
        text.setPos((iv.start + iv.end) / 2.0, 0.5)
        self.plot.addItem(region)
        self.plot.addItem(text)
        item = _LabelItem(region, text, iv)
        if self.editable:
            region.sigRegionChangeFinished.connect(lambda _r, it=item: self._on_region_changed(it))
        self._items.append(item)
        self._style_region(region, selected=False)
        return item

    def _on_region_changed(self, item: _LabelItem) -> None:
        a, b = item.region.getRegion()
        item.interval = Interval(min(a, b), max(a, b), item.interval.label)
        item.text.setPos((a + b) / 2.0, 0.5)
        self.tier_changed.emit()

    def _emit_active(self) -> None:
        self.label_selected.emit(self.active_interval())

    def _style_region(self, region, selected: bool) -> None:
        accent = self._theme.color("accent")
        fill = QColor(accent if selected else _UNSEL)
        fill.setAlpha(120 if selected else 60)
        region.setBrush(pg.mkBrush(fill))
        pen = pg.mkPen(accent if selected else _UNSEL, width=2 if selected else 1)
        for line in region.lines:
            line.setPen(pen)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.plot.getViewBox().setBackgroundColor(theme.color("panel"))
        for i, it in enumerate(self._items):
            self._style_region(it.region, selected=(i == self._active))
            it.text.setColor(theme.color("text-pri"))
