"""Label lane with viewport virtualization.

A tier may hold hundreds of intervals (cue/condition/MFA tiers ~ one per trial). Creating a
graphics item per interval melts the scene, so this lane keeps the data in a plain list and only
binds a small recycled pool of region+text items to the intervals currently in view (capped, with
text shown only when sparse). Pan/zoom rebinds the pool; cost is ~ visible labels, not total.
"""

from __future__ import annotations

import math

import pyqtgraph as pg
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from rpcoding.core.labels import Interval, Tier
from rpcoding.gui.theme import Theme

LABEL_LANE_HEIGHT = 46
_MAX_RENDER = 120  # hard cap on region items rendered per lane (sampled beyond this)
_TEXT_LIMIT = 80  # show interval text only when at most this many are rendered
_CHAR_PX = 7.5  # rough mono glyph width, to decide if a label's text fits inside it


class _PoolItem:
    __slots__ = ("region", "text", "idx")

    def __init__(self, region, text):
        self.region = region
        self.text = text
        self.idx = -1


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
        self._intervals: list[Interval] = []
        self._active = -1  # index into _intervals
        self._pool: list[_PoolItem] = []
        self._used = 0
        self._view = (0.0, 1.0)
        self._px = 1
        self._binding = False

        vb = plot.getViewBox()
        vb.setMenuEnabled(False)
        vb.enableAutoRange(x=False, y=False)
        plot.setYRange(0.0, 1.0, padding=0)
        self.apply_theme(theme)

    # ---- tier I/O ----
    def set_tier(self, tier: Tier) -> None:
        self._intervals = list(tier.intervals)
        self._active = -1
        self._render()

    def get_tier(self) -> Tier:
        return Tier(self.name, sorted(self._intervals, key=lambda i: i.start))

    def intervals(self) -> list[Interval]:
        return list(self._intervals)

    # ---- editing ----
    def create(self, start: float, end: float, label: str = "") -> Interval:
        iv = Interval(min(start, end), max(start, end), label)
        self._intervals.append(iv)
        self._active = len(self._intervals) - 1
        self.tier_changed.emit()
        self._render()
        self._emit_active()
        return iv

    def delete_active(self) -> None:
        if not (0 <= self._active < len(self._intervals)):
            return
        del self._intervals[self._active]
        self._active = min(self._active, len(self._intervals) - 1)
        self.tier_changed.emit()
        self._render()
        self._emit_active()

    def rename_active(self, label: str) -> None:
        if not (0 <= self._active < len(self._intervals)):
            return
        iv = self._intervals[self._active]
        self._intervals[self._active] = Interval(iv.start, iv.end, label)
        self.tier_changed.emit()
        self._render()

    # ---- selection / navigation ----
    def select(self, index: int) -> None:
        self._active = index if 0 <= index < len(self._intervals) else -1
        self._render()
        self._emit_active()

    def active_interval(self) -> Interval | None:
        if 0 <= self._active < len(self._intervals):
            return self._intervals[self._active]
        return None

    def select_step(self, step: int) -> Interval | None:
        """Select next (step>0) / previous (step<0) label by start time; wraps."""
        if not self._intervals:
            return None
        order = sorted(range(len(self._intervals)), key=lambda i: self._intervals[i].start)
        if self._active < 0:
            new = order[0] if step > 0 else order[-1]
        else:
            pos = order.index(self._active)
            new = order[(pos + (1 if step > 0 else -1)) % len(order)]
        self.select(new)
        return self._intervals[new]

    def select_at(self, x: float) -> Interval | None:
        """Select the interval containing time ``x`` (deselect if none); return it or None."""
        hit = next((i for i, iv in enumerate(self._intervals) if iv.start <= x <= iv.end), -1)
        self.select(hit)
        return self._intervals[hit] if hit >= 0 else None

    def clear(self) -> None:
        for item in self._pool:
            self.plot.removeItem(item.region)
            self.plot.removeItem(item.text)
        self._pool = []
        self._used = 0
        self._intervals = []
        self._active = -1

    # ---- virtualized rendering ----
    def set_view(self, t0: float, t1: float, px: int) -> None:
        self._view = (t0, t1)
        self._px = px
        self._render()

    def _visible_indices(self) -> list[int]:
        t0, t1 = self._view
        idxs = [i for i, iv in enumerate(self._intervals) if iv.end >= t0 and iv.start <= t1]
        if len(idxs) > _MAX_RENDER:
            stride = math.ceil(len(idxs) / _MAX_RENDER)
            sampled = idxs[::stride]
            if 0 <= self._active < len(self._intervals) and self._active in idxs:
                if self._active not in sampled:
                    sampled.append(self._active)
            idxs = sampled
        return idxs

    def _render(self) -> None:
        idxs = self._visible_indices()
        show_text = len(idxs) <= _TEXT_LIMIT
        for slot, idx in enumerate(idxs):
            self._bind(self._slot(slot), idx, show_text)
        for slot in range(len(idxs), self._used):
            self._pool[slot].region.hide()
            self._pool[slot].text.hide()
        self._used = len(idxs)

    def _slot(self, slot: int) -> _PoolItem:
        while slot >= len(self._pool):
            # Movable only while selected (set in _bind), so plain clicks reach the lane to select.
            region = pg.LinearRegionItem(values=[0, 0], movable=False)
            region.setZValue(10)
            text = pg.TextItem("", anchor=(0.5, 0.5), color=self._theme.color("label-text"))
            self.plot.addItem(region)
            self.plot.addItem(text)
            item = _PoolItem(region, text)
            if self.editable:
                region.sigRegionChanged.connect(lambda _r, it=item: self._on_region_changing(it))
                region.sigRegionChangeFinished.connect(
                    lambda _r, it=item: self._on_region_finished(it)
                )
            self._pool.append(item)
        return self._pool[slot]

    def _bind(self, item: _PoolItem, idx: int, show_text: bool) -> None:
        iv = self._intervals[idx]
        item.idx = idx
        self._binding = True
        item.region.setRegion((iv.start, iv.end))
        self._binding = False
        item.region.setMovable(self.editable and idx == self._active)  # drag only when selected
        item.region.show()
        selected = idx == self._active
        self._style_region(item.region, selected=selected)
        if show_text and iv.label:
            item.text.setText(iv.label)
            item.text.setColor(self._theme.color("text-pri" if selected else "label-text"))
            item.text.setPos((iv.start + iv.end) / 2.0, self._text_y(iv.start, iv.end, iv.label))
            item.text.show()
        else:
            item.text.hide()

    def _text_y(self, start: float, end: float, label: str) -> float:
        """0.5 (centred on the chip) if the text fits, else 0.14 (tucked just below it)."""
        t0, t1 = self._view
        if t1 > t0 and self._px > 0:
            label_px = (end - start) / (t1 - t0) * self._px
            if label_px < len(label) * _CHAR_PX + 6:
                return 0.14
        return 0.5

    def _on_region_changing(self, item: _PoolItem) -> None:
        """Live during a drag: update the interval + cross-lane highlight (no tier_changed yet)."""
        if self._binding or not (0 <= item.idx < len(self._intervals)):
            return
        a, b = item.region.getRegion()
        old = self._intervals[item.idx]
        self._intervals[item.idx] = Interval(min(a, b), max(a, b), old.label)
        item.text.setPos((a + b) / 2.0, self._text_y(a, b, old.label))
        if item.idx == self._active:
            self._emit_active()  # highlight follows the drag in real time

    def _on_region_finished(self, item: _PoolItem) -> None:
        """Drag released: the interval is already current; mark the tier changed (save/undo)."""
        if self._binding or not (0 <= item.idx < len(self._intervals)):
            return
        self.tier_changed.emit()

    def _emit_active(self) -> None:
        self.label_selected.emit(self.active_interval())

    def _style_region(self, region, selected: bool) -> None:
        if selected:
            fill = QColor(self._theme.color("accent"))
            fill.setAlpha(64)
            pen = pg.mkPen(self._theme.color("accent"), width=2)
        else:
            fill = QColor(self._theme.color("label-bg"))
            fill.setAlpha(190)
            pen = pg.mkPen(self._theme.color("label-border"), width=1)
        region.setBrush(pg.mkBrush(fill))
        for line in region.lines:
            line.setPen(pen)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        bg = theme.color("response-bg" if self.editable else "lane-bg")
        self.plot.getViewBox().setBackgroundColor(bg)
        for item in self._pool[: self._used]:
            selected = item.idx == self._active
            self._style_region(item.region, selected=selected)
            item.text.setColor(theme.color("text-pri" if selected else "label-text"))
