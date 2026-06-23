"""AudioEditor: stacked waveform + spectrogram + label lanes on one shared time axis.

Adds the label-tracks layer: tier rendering, a selection span mirrored across lanes, a Trial Info
side panel, and keyboard editing (Ctrl+B create, Tab/Shift+Tab navigate, Delete remove).
"""

from __future__ import annotations

from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QVBoxLayout, QWidget

from rpcoding.core.audio.io import duration_seconds
from rpcoding.core.audio.render.cache import AudioRenderCache
from rpcoding.core.labels import Tier, write_tier
from rpcoding.core.trial_index import TrialIndex
from rpcoding.gui.editor.debounce import RangeDebouncer
from rpcoding.gui.editor.interactive_viewbox import InteractiveViewBox
from rpcoding.gui.editor.label_lane import LABEL_LANE_HEIGHT, LabelLane
from rpcoding.gui.editor.render_jobs import build_pyramid_job, build_spectrogram_job
from rpcoding.gui.editor.selection import SelectionModel
from rpcoding.gui.editor.spectrogram_lane import SpectrogramLane
from rpcoding.gui.editor.toolbar import EditorToolbar
from rpcoding.gui.editor.trial_info_panel import TrialInfoPanel
from rpcoding.gui.editor.waveform_lane import WaveformLane
from rpcoding.gui.theme import DARK_THEME, Theme
from rpcoding.gui.workers.worker import run_in_thread

pg.setConfigOptions(imageAxisOrder="row-major")

_NAME_W = 104  # width of the left track-name column
_RULER_H = 26
_LANE_H = 132
_INITIAL_VIEW_S = 60.0  # open zoomed to this window (fast first render); Fit shows the whole file


class TimeAxisItem(pg.AxisItem):
    """Bottom axis that formats seconds as ``m:ss.mmm``."""

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            v = max(float(v), 0.0)
            m = int(v // 60)
            out.append(f"{m:d}:{v - 60 * m:06.3f}")
        return out


class AudioEditor(QWidget):
    range_changed = Signal(float, float)
    selection_changed = Signal(object)
    load_finished = Signal()
    load_failed = Signal(str)
    saved = Signal()
    back_requested = Signal()
    # Internal: the render workers emit these (cross-thread); connected to UI-thread slots so the
    # actual pyqtgraph work always runs on the GUI thread (touching graphics off-thread crashes Qt).
    _pyramid_ready = Signal(int, object, object)  # token, pyramid, wav_path
    _spectro_ready = Signal(int, object)  # token, handle

    def __init__(self, theme: Theme = DARK_THEME, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._theme = theme
        self._duration = 0.0
        self._load_token = 0
        self._pyr_ok = False
        self._spec_ok = False
        self._jobs: list = []
        self._label_lanes: list[LabelLane] = []
        self._lane_plots: list[pg.PlotItem] = []
        self._lane_labels: list[pg.LabelItem] = []
        self._focus_lane: LabelLane | None = None
        self._active_lane: LabelLane | None = None  # lane whose label is currently selected
        self._trial_index: TrialIndex | None = None
        self._save_path: Path | None = None
        self._row = 0
        self._sel_updating = False
        self._sel_regions: list[pg.LinearRegionItem] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._toolbar = EditorToolbar()
        self._toolbar.amplitude_changed.connect(self.set_amplitude_scale)
        self._toolbar.save_requested.connect(self.save)
        self._toolbar.back_requested.connect(self.back_requested.emit)
        self._toolbar.zoom_in_requested.connect(lambda: self.zoom(0.6))
        self._toolbar.zoom_out_requested.connect(lambda: self.zoom(1.7))
        self._toolbar.fit_requested.connect(self.fit)
        outer.addWidget(self._toolbar)

        body = QHBoxLayout()
        outer.addLayout(body, 1)
        self._glw = pg.GraphicsLayoutWidget()
        body.addWidget(self._glw, 1)
        self._glw.scene().sigMouseClicked.connect(self._on_scene_click)
        self._trial_panel = TrialInfoPanel()
        self._trial_panel.error_code_picked.connect(self._on_error_code)
        body.addWidget(self._trial_panel)

        self._glw.ci.layout.setColumnFixedWidth(0, _NAME_W)  # the track-name column
        self._glw.ci.layout.setColumnStretchFactor(1, 1)  # plots take the rest

        self._ruler = self._add_row(
            "",
            _RULER_H,
            axis={"bottom": TimeAxisItem(orientation="bottom")},
            viewbox=InteractiveViewBox(),
        )
        self._wave_plot = self._add_row("Waveform", _LANE_H, viewbox=InteractiveViewBox())
        self._wave_plot.hideAxis("bottom")
        self._owner_vb = self._wave_plot.getViewBox()
        self._wire_vb(self._owner_vb)
        self.waveform = WaveformLane(self._wave_plot, theme)

        self._spec_plot = self._add_row("Spectrogram", _LANE_H, viewbox=InteractiveViewBox())
        self._spec_plot.hideAxis("bottom")
        self._hist = pg.HistogramLUTItem()
        self._glw.addItem(self._hist, row=self._row - 1, col=2)
        self.spectrogram = SpectrogramLane(self._spec_plot, self._hist, theme)

        for plot in (self._ruler, self._spec_plot):
            plot.setXLink(self._wave_plot)
        self._wire_vb(self._ruler.getViewBox())
        self._wire_vb(self._spec_plot.getViewBox())
        self._base_row = self._row  # first row available for label lanes (after ruler/wave/spec)

        # selection: a span set by left-drag on the waveform, mirrored read-only across all lanes.
        self._sel = SelectionModel(self)
        self._sel.changed.connect(self._on_selection_changed)
        self._sel_master = self._make_sel_region(self._wave_plot, movable=False)
        self._add_mirror_region(self._spec_plot)

        self._debouncer = RangeDebouncer(40, self)
        self._debouncer.flushed.connect(self._reslice_all)
        self._owner_vb.sigXRangeChanged.connect(self._on_x_range)

        # Worker results are marshalled onto the UI thread via these (queued) connections.
        self._pyramid_ready.connect(self._on_pyramid)
        self._spectro_ready.connect(self._on_spectro)

    # ---- layout ----
    def _add_row(
        self, name: str, height: int, axis: dict | None = None, viewbox=None
    ) -> pg.PlotItem:
        """Add a row: a horizontal name label in col 0 and the plot (no left axis) in col 1."""
        label = pg.LabelItem(name, justify="left", size="9pt", color=self._theme.color("text-sec"))
        self._glw.addItem(label, row=self._row, col=0)
        plot = self._glw.addPlot(row=self._row, col=1, axisItems=axis or {}, viewBox=viewbox)
        self._row += 1
        plot.setMinimumHeight(height)
        plot.setMaximumHeight(height)
        plot.hideAxis("left")  # no y scale on any lane; the name lives in col 0
        plot.getViewBox().setMenuEnabled(False)
        plot._name_label = label  # keep a handle so label lanes can be torn down with their label
        return plot

    def _wire_vb(self, vb: InteractiveViewBox) -> None:
        vb.region_selected.connect(self._on_drag_select)
        vb.zoom_requested.connect(self._zoom_at)
        vb.pan_requested.connect(self._pan)

    def _make_sel_region(self, plot: pg.PlotItem, movable: bool) -> pg.LinearRegionItem:
        fill = QColor(self._theme.color("accent"))
        fill.setAlpha(40)
        region = pg.LinearRegionItem(movable=movable, brush=pg.mkBrush(fill))
        region.setZValue(5)
        region.hide()
        plot.addItem(region)
        return region

    def _add_mirror_region(self, plot: pg.PlotItem) -> None:
        self._sel_regions.append(self._make_sel_region(plot, movable=False))

    # ---- public API ----
    def duration(self) -> float:
        return self._duration

    def visible_range(self) -> tuple[float, float]:
        x0, x1 = self._owner_vb.viewRange()[0]
        return float(x0), float(x1)

    def set_visible_range(self, t0: float, t1: float) -> None:
        self._owner_vb.setXRange(t0, t1, padding=0)

    def set_amplitude_scale(self, gain: float) -> None:
        self.waveform.set_gain(gain)

    def zoom(self, factor: float) -> None:
        """Zoom the time axis about the view centre (factor < 1 zooms in)."""
        t0, t1 = self.visible_range()
        centre = (t0 + t1) / 2.0
        half = max((t1 - t0) * factor / 2.0, 1e-4)
        lo = max(centre - half, 0.0)
        hi = centre + half
        if self._duration:
            hi = min(hi, self._duration)
        self.set_visible_range(lo, hi)

    def fit(self) -> None:
        self.set_visible_range(0.0, self._duration or 1.0)

    def _zoom_at(self, centre: float, factor: float) -> None:
        """Zoom the time axis about ``centre`` (the cursor) — Ctrl+wheel."""
        t0, t1 = self.visible_range()
        n0 = centre - (centre - t0) * factor
        n1 = centre + (t1 - centre) * factor
        if self._duration:
            n0 = max(n0, 0.0)
            n1 = min(n1, self._duration)
        if n1 - n0 > 1e-4:
            self.set_visible_range(n0, n1)

    def _pan(self, frac: float) -> None:
        """Shift the time axis by a fraction of the view width — Shift+wheel."""
        t0, t1 = self.visible_range()
        width = t1 - t0
        n0, n1 = t0 + frac * width, t1 + frac * width
        if self._duration:
            if n0 < 0:
                n0, n1 = 0.0, width
            elif n1 > self._duration:
                n0, n1 = self._duration - width, self._duration
        self.set_visible_range(n0, n1)

    def set_db_range(self, lo: float, hi: float) -> None:
        self.spectrogram.set_db_levels(lo, hi)

    def selection(self) -> tuple[float, float] | None:
        return self._sel.span()

    def set_selection(self, span: tuple[float, float] | None) -> None:
        self._sel.set_span(span)

    def add_label_lane(self, name: str, editable: bool = False) -> LabelLane:
        plot = self._add_row(
            name + (" ✎" if editable else ""), LABEL_LANE_HEIGHT, viewbox=InteractiveViewBox()
        )
        plot.hideAxis("bottom")
        plot.setXLink(self._wave_plot)
        self._wire_vb(plot.getViewBox())
        lane = LabelLane(plot, name, self._theme, editable=editable)
        lane.label_selected.connect(lambda iv, ln=lane: self._on_label_selected(ln, iv))
        self._label_lanes.append(lane)
        self._lane_plots.append(plot)
        self._lane_labels.append(plot._name_label)
        self._add_mirror_region(plot)
        if editable and self._focus_lane is None:
            self._focus_lane = lane
        return lane

    def clear_tiers(self) -> None:
        """Remove all label lanes and reset selection/trial state (for reopening on a new step)."""
        self.set_selection(None)
        for plot in self._lane_plots:
            self._glw.removeItem(plot)
        for label in self._lane_labels:
            self._glw.removeItem(label)
        self._label_lanes = []
        self._lane_plots = []
        self._lane_labels = []
        self._focus_lane = None
        self._trial_index = None
        del self._sel_regions[1:]  # keep only the spectrogram mirror (added in __init__)
        self._row = self._base_row

    def set_tiers(
        self,
        tiers: list[tuple[str, Tier, bool]],
        cue_name: str = "cue_events",
        condition_name: str = "condition_events",
    ) -> None:
        """Populate label lanes from ``(name, tier, editable)`` and build the trial index.

        Clears any previously loaded tiers first, so reopening the editor never stacks lanes.
        """
        self.clear_tiers()
        by_name: dict[str, Tier] = {}
        for name, tier, editable in tiers:
            lane = self.add_label_lane(name, editable=editable)
            lane.set_tier(tier)
            by_name[name] = tier
        if cue_name in by_name:
            self._trial_index = TrialIndex(by_name[cue_name], by_name.get(condition_name))

    # ---- saving ----
    def configure_save(self, path: Path | str | None) -> None:
        """Set where :meth:`save` writes the editable tier (Audacity ``.txt``)."""
        self._save_path = Path(path) if path is not None else None

    def save(self) -> None:
        """Write the editable (focused) tier to the configured path and emit ``saved``."""
        if self._save_path is None or self._focus_lane is None:
            return
        write_tier(self._focus_lane.get_tier(), self._save_path)
        self._toolbar.set_status(f"Saved → {self._save_path.name}")
        self.saved.emit()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.waveform.apply_theme(theme)
        self.spectrogram.apply_theme(theme)
        for lane in self._label_lanes:
            lane.apply_theme(theme)

    def load(self, wav_path, cache_dir=None) -> None:
        wav_path = Path(wav_path)
        self._duration = duration_seconds(wav_path)
        # Open zoomed in so only a handful of labels render on open (no full-file render freeze).
        self.set_visible_range(0.0, min(self._duration, _INITIAL_VIEW_S) or 1.0)
        cache_root = Path(cache_dir) if cache_dir else wav_path.parent / ".rpcoding" / "cache"
        content_key = AudioRenderCache(cache_root).content_key(wav_path)

        self._load_token += 1
        token = self._load_token
        self._pyr_ok = self._spec_ok = False
        self._toolbar.set_progress(0, "Building waveform + spectrogram…")

        self._jobs.append(
            run_in_thread(
                self,
                build_pyramid_job,
                wav_path,
                cache_root,
                content_key,
                on_result=lambda pyr, tk=token, w=wav_path: self._pyramid_ready.emit(tk, pyr, w),
                on_error=self.load_failed.emit,
            )
        )
        self._jobs.append(
            run_in_thread(
                self,
                build_spectrogram_job,
                wav_path,
                cache_root,
                content_key,
                on_result=lambda handle, tk=token: self._spectro_ready.emit(tk, handle),
                on_error=self.load_failed.emit,
            )
        )

    def clear(self) -> None:
        self.spectrogram.close_source()

    # ---- keyboard editing ----
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if ctrl and key == Qt.Key.Key_S:
            self.save()
        elif ctrl and key == Qt.Key.Key_B:
            self._create_label_from_selection()
        elif key == Qt.Key.Key_Escape:
            self.close()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._rename_active()
        elif key == Qt.Key.Key_Tab:
            self._navigate(1)
        elif key == Qt.Key.Key_Backtab:
            self._navigate(-1)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_active()
        else:
            super().keyPressEvent(event)

    def _create_label_from_selection(self) -> None:
        span = self._sel.span()
        if span is None or self._focus_lane is None:
            return
        self._select_only(self._focus_lane)
        self._focus_lane.create(span[0], span[1])

    def _navigate(self, step: int) -> None:
        if self._focus_lane is None:
            return
        self._select_only(self._focus_lane)
        iv = self._focus_lane.select_step(step)
        if iv is not None:
            self._center_on(iv.start, iv.end)

    # ---- label selection / editing ----
    def _select_only(self, lane: LabelLane | None) -> None:
        """Make ``lane`` the active selection, clearing any selection on the other lanes."""
        for other in self._label_lanes:
            if other is not lane:
                other.select(-1)
        self._active_lane = lane

    def _on_scene_click(self, ev) -> None:
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.scenePos()
        for lane in self._label_lanes:
            vb = lane.plot.getViewBox()
            if vb.sceneBoundingRect().contains(pos):
                self._select_only(lane)
                lane.select_at(vb.mapSceneToView(pos).x())  # emits label_selected -> highlight
                return
        self._select_only(None)  # clicked an audio lane / empty -> deselect labels
        self.set_selection(None)

    def _on_label_selected(self, lane: LabelLane, iv) -> None:
        if lane is not self._active_lane:
            return  # an incidental deselect on a non-active lane
        self.set_selection((iv.start, iv.end) if iv is not None else None)

    def _rename_active(self) -> None:
        lane = self._active_lane
        if lane is None or not lane.editable or lane.active_interval() is None:
            return
        text, ok = QInputDialog.getText(
            self, "Rename label", "Label:", text=lane.active_interval().label
        )
        if ok:
            lane.rename_active(text)

    def _on_error_code(self, code: str) -> None:
        lane = self._active_lane
        if lane is None or not lane.editable:
            return
        iv = lane.active_interval()
        if iv is None:
            return
        lane.rename_active(f"{iv.label}/{code}" if iv.label else code)  # append the code

    def _delete_active(self) -> None:
        lane = self._active_lane
        if lane is not None and lane.editable:
            lane.delete_active()

    def _center_on(self, a: float, b: float) -> None:
        """Scroll the view to show [a, b] (keeping the current zoom width) if it's off-screen."""
        t0, t1 = self.visible_range()
        if t0 <= a and b <= t1:
            return
        width = max(t1 - t0, b - a)
        centre = (a + b) / 2.0
        self.set_visible_range(max(centre - width / 2.0, 0.0), centre + width / 2.0)

    # ---- selection ----
    def _on_drag_select(self, x0: float, x1: float) -> None:
        if abs(x1 - x0) < 1e-6:
            return  # degenerate drag; real clicks arrive via the scene's sigMouseClicked
        self._select_only(None)  # a fresh time-drag clears any selected label
        self.set_selection((min(x0, x1), max(x0, x1)))

    def _on_selection_changed(self, span) -> None:
        self._sel_updating = True
        try:
            regions = [self._sel_master, *self._sel_regions]
            if span is None:
                for r in regions:
                    r.hide()
            else:
                for r in regions:
                    r.setRegion(span)
                    r.show()
        finally:
            self._sel_updating = False
        if span is not None and self._trial_index is not None:
            mid = (span[0] + span[1]) / 2.0
            self._trial_panel.set_trial(self._trial_index.at(mid))
        elif span is None:
            self._trial_panel.set_trial(None)
        self._toolbar.set_selection_text(span)
        self.selection_changed.emit(span)

    # ---- render ----
    def _on_pyramid(self, token: int, pyr, wav_path) -> None:
        if token != self._load_token:
            return
        self.waveform.set_source(pyr, wav_path)
        self._pyr_ok = True
        self._refresh()
        self._maybe_finished()

    def _on_spectro(self, token: int, handle: dict) -> None:
        if token != self._load_token:
            return
        self.spectrogram.set_source(handle["spec_path"], handle["meta"])
        self._spec_ok = True
        self._refresh()
        self._maybe_finished()

    def _maybe_finished(self) -> None:
        if self._pyr_ok and self._spec_ok:
            self._toolbar.build_done()
            self.load_finished.emit()

    def _on_x_range(self, _vb, rng) -> None:
        px = max(int(self._owner_vb.width()), 1)
        self._debouncer.request(float(rng[0]), float(rng[1]), px)

    def _refresh(self) -> None:
        t0, t1 = self.visible_range()
        self._reslice_all(t0, t1, max(int(self._owner_vb.width()), 1))

    def _reslice_all(self, t0: float, t1: float, px: int) -> None:
        self.waveform.set_view(t0, t1, px)
        self.spectrogram.set_view(t0, t1, px)
        for lane in self._label_lanes:
            lane.set_view(t0, t1, px)
        self.range_changed.emit(t0, t1)
