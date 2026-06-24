"""AudioEditor: stacked waveform + spectrogram + label lanes on one shared time axis.

Adds the label-tracks layer: tier rendering, a selection span mirrored across lanes, a Trial Info
side panel, and keyboard editing (Ctrl+B create, Tab/Shift+Tab navigate, Delete remove).
"""

from __future__ import annotations

from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QVBoxLayout, QWidget

from rpcoding.core.audio.io import duration_seconds
from rpcoding.core.audio.render.cache import AudioRenderCache
from rpcoding.core.labels import Interval, Tier, write_tier
from rpcoding.core.trial_index import TrialIndex
from rpcoding.gui.editor.debounce import RangeDebouncer
from rpcoding.gui.editor.header_column import LaneHeaderColumn
from rpcoding.gui.editor.interactive_viewbox import InteractiveViewBox
from rpcoding.gui.editor.label_lane import LABEL_LANE_HEIGHT, LabelLane
from rpcoding.gui.editor.playback import AudioPlayer
from rpcoding.gui.editor.render_jobs import build_pyramid_job, build_spectrogram_job
from rpcoding.gui.editor.selection import SelectionModel
from rpcoding.gui.editor.spectrogram_lane import SpectrogramLane
from rpcoding.gui.editor.toolbar import EditorToolbar
from rpcoding.gui.editor.trial_info_panel import TrialInfoPanel
from rpcoding.gui.editor.waveform_lane import WaveformLane
from rpcoding.gui.theme import DARK_THEME, Theme
from rpcoding.gui.workers.worker import run_in_thread

pg.setConfigOptions(imageAxisOrder="row-major")

_RULER_H = 26
_WAVE_H = 100  # waveform a bit shorter ...
_SPEC_H = 176  # ... spectrogram taller
_SPACER_ROW = 64  # a reserved high GLW row holding the bottom stretch (keeps fixed rows top-packed)
_INITIAL_VIEW_S = 60.0  # open zoomed to this window (fast first render); Fit shows the whole file

# Friendly left-column names for the lanes (the internal tier name still drives the trial index).
_LANE_DISPLAY = {
    "first_stims": "first stim",
    "condition_events": "condition",
    "cue_events": "cue",
    "response": "response",
    "mfa_resp_words": "MFA resp",
    "mfa_stim_words": "MFA stim",
}


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
    theme_toggle_requested = Signal()  # the toolbar ◑ button; the app flips dark/light
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
        self._focus_lane: LabelLane | None = None
        self._active_lane: LabelLane | None = None  # lane whose label is currently selected
        self._amp_scale = 1.0
        self._trial_index: TrialIndex | None = None
        self._save_path: Path | None = None
        self._clipboard: Interval | None = None
        self._undo_stack: list[list[Interval]] = []  # snapshots of the editable tier
        self._undo_idx = 0
        self._restoring = False
        self._cursor: float | None = None
        self._wav_path: Path | None = None
        self._row = 0
        self._sel_updating = False
        self._sel_regions: list[pg.LinearRegionItem] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._toolbar = EditorToolbar()
        self._toolbar.save_requested.connect(self.save)
        self._toolbar.back_requested.connect(self.back_requested.emit)
        self._toolbar.zoom_in_requested.connect(lambda: self.zoom(0.6))
        self._toolbar.zoom_out_requested.connect(lambda: self.zoom(1.7))
        self._toolbar.fit_requested.connect(self.fit)
        self._toolbar.selection_edited.connect(self._on_selection_edited)
        self._toolbar.play_requested.connect(self._toggle_play)
        self._toolbar.volume_changed.connect(self._on_volume_changed)
        self._toolbar.add_label_requested.connect(self._create_label_from_selection)
        self._toolbar.copy_requested.connect(self._copy_active)
        self._toolbar.paste_requested.connect(self._paste)
        self._toolbar.theme_toggle_requested.connect(self.theme_toggle_requested.emit)
        outer.addWidget(self._toolbar)

        # body = [170px header column | plot column (pyqtgraph) | 272px Trial Info]
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        self._header = LaneHeaderColumn(theme, _RULER_H, _WAVE_H, _SPEC_H)
        self._header.amp_up.connect(lambda: self._nudge_amp(1.3))
        self._header.amp_down.connect(lambda: self._nudge_amp(0.77))
        body.addWidget(self._header)

        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setFrameShape(QFrame.Shape.NoFrame)
        self._glw.setBackground(theme.color("lane-bg"))
        self._glw.ci.layout.setContentsMargins(0, 0, 0, 0)
        self._glw.ci.layout.setSpacing(0)  # rows abut; heights match the header column exactly
        body.addWidget(self._glw, 1)
        self._glw.scene().sigMouseClicked.connect(self._on_scene_click)

        self._trial_panel = TrialInfoPanel()
        self._trial_panel.error_code_picked.connect(self._on_error_code)
        body.addWidget(self._trial_panel)

        self._glw.ci.layout.setColumnStretchFactor(0, 1)  # col 0 = plots; col 1 = histogram
        # a reserved high row holds the bottom stretch, so the fixed rows stay packed at the top
        self._glw.addItem(pg.GraphicsLayout(), row=_SPACER_ROW, col=0)
        self._glw.ci.layout.setRowStretchFactor(_SPACER_ROW, 1)

        self._ruler = self._add_row(
            _RULER_H,
            axis={"bottom": TimeAxisItem(orientation="bottom")},
            viewbox=InteractiveViewBox(),
        )
        self._wave_plot = self._add_row(_WAVE_H, viewbox=InteractiveViewBox())
        self._wave_plot.hideAxis("bottom")
        self._owner_vb = self._wave_plot.getViewBox()
        self._wire_vb(self._owner_vb)
        self.waveform = WaveformLane(self._wave_plot, theme)

        self._spec_plot = self._add_row(_SPEC_H, viewbox=InteractiveViewBox())
        self._spec_plot.hideAxis("bottom")
        self._hist = pg.HistogramLUTItem()
        # Cap the histogram to the spectrogram row height; otherwise its natural height inflates the
        # whole row and the label lanes drift out of step with the (fixed-height) header column.
        self._hist.setMaximumHeight(_SPEC_H)
        self._glw.addItem(self._hist, row=self._row - 1, col=1)
        self.spectrogram = SpectrogramLane(self._spec_plot, self._hist, theme)

        for plot in (self._ruler, self._spec_plot):
            plot.setXLink(self._wave_plot)
        self._wire_vb(self._ruler.getViewBox())
        self._wire_vb(self._spec_plot.getViewBox())
        self._base_row = self._row  # first row available for label lanes (after ruler/wave/spec)

        # selection: a span set by left-drag, mirrored read-only across all lanes; a click cursor.
        self._sel = SelectionModel(self)
        self._sel.changed.connect(self._on_selection_changed)
        self._sel_master = self._make_sel_region(self._wave_plot, movable=True)
        self._add_mirror_region(self._spec_plot, movable=True)
        self._cursor_master = self._make_cursor_line(self._wave_plot)
        self._cursor_lines: list = []
        self._add_cursor_line(self._spec_plot)
        self._drag_mode = "new"  # "new" | "move"
        self._drag_anchor: tuple[float, float] | None = None

        self._glw.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep Tab on the editor (label nav)

        self._debouncer = RangeDebouncer(40, self)
        self._debouncer.flushed.connect(self._reslice_all)
        self._owner_vb.sigXRangeChanged.connect(self._on_x_range)

        # Worker results are marshalled onto the UI thread via these (queued) connections.
        self._pyramid_ready.connect(self._on_pyramid)
        self._spectro_ready.connect(self._on_spectro)

        # playback: the cursor doubles as the playhead, advanced by a UI-thread timer.
        self._player = AudioPlayer(self)
        self._player.finished.connect(self._on_playback_finished)
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(30)
        self._play_timer.timeout.connect(self._update_playhead)

    # ---- layout ----
    def _add_row(self, height: int, axis: dict | None = None, viewbox=None) -> pg.PlotItem:
        """Add a fixed-height plot row in col 0 (the track name lives in the header column)."""
        plot = self._glw.addPlot(row=self._row, col=0, axisItems=axis or {}, viewBox=viewbox)
        self._row += 1
        plot.setMinimumHeight(height)
        plot.setMaximumHeight(height)
        plot.hideAxis("left")  # no y scale on any lane
        plot.getViewBox().setMenuEnabled(False)
        return plot

    def _wire_vb(self, vb: InteractiveViewBox) -> None:
        vb.region_dragged.connect(self._on_region_dragged)
        vb.zoom_requested.connect(self._zoom_at)
        vb.pan_requested.connect(self._pan)

    def _make_sel_region(self, plot: pg.PlotItem, movable: bool) -> pg.LinearRegionItem:
        fill = QColor(self._theme.color("accent"))
        fill.setAlpha(40)
        region = pg.LinearRegionItem(movable=movable, brush=pg.mkBrush(fill))
        region.setZValue(5)
        region.hide()
        plot.addItem(region)
        if movable:  # drag the body to move the selection, an edge to resize it
            region.sigRegionChanged.connect(lambda _r, r=region: self._on_sel_region_changed(r))
        return region

    def _add_mirror_region(self, plot: pg.PlotItem, movable: bool = False) -> None:
        self._sel_regions.append(self._make_sel_region(plot, movable=movable))

    def _on_sel_region_changed(self, region: pg.LinearRegionItem) -> None:
        if self._sel_updating:
            return  # programmatic update from _on_selection_changed; don't echo
        a, b = region.getRegion()
        self._sel.set_span((min(a, b), max(a, b)))

    def _make_cursor_line(self, plot: pg.PlotItem) -> pg.InfiniteLine:
        pen = pg.mkPen(self._theme.color("accent"), width=1, style=Qt.PenStyle.DashLine)
        line = pg.InfiniteLine(angle=90, movable=False, pen=pen)
        line.setZValue(6)
        line.hide()
        plot.addItem(line)
        return line

    def _add_cursor_line(self, plot: pg.PlotItem) -> None:
        self._cursor_lines.append(self._make_cursor_line(plot))

    def set_cursor(self, x: float | None) -> None:
        """Show a vertical cursor at time ``x`` across all lanes (None hides it)."""
        self._cursor = x
        for line in (self._cursor_master, *self._cursor_lines):
            if x is None:
                line.hide()
            else:
                line.setPos(x)
                line.show()

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

    def _nudge_amp(self, factor: float) -> None:
        """Step the waveform amplitude (the header ＋/－ buttons), clamped to 0.1x..10x."""
        self._amp_scale = max(0.1, min(10.0, self._amp_scale * factor))
        self.set_amplitude_scale(self._amp_scale)

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

    def _on_selection_edited(self, a: float, b: float) -> None:
        self.set_selection((a, b))
        self.setFocus()  # return keyboard focus to the editor after typing in a readout field

    # ---- playback ----
    def _play_range(self) -> tuple[float, float | None]:
        """The window Space/Play uses: the selection, else cursor-to-end, else the whole file."""
        span = self._sel.span()
        if span is not None:
            return span[0], span[1]
        if self._cursor is not None:
            return self._cursor, None  # from the cursor to the end
        return 0.0, None  # the whole file

    def _toggle_play(self) -> None:
        if self._player.is_playing():
            self._player.stop()  # -> finished -> the cursor is left at the stop position
            return
        if self._wav_path is None or not self._wav_path.exists():
            return
        start, end = self._play_range()
        self._player.play(self._wav_path, start, end)
        if self._player.is_playing():
            self._toolbar.set_playing(True)
            self.set_cursor(start)  # the cursor doubles as the playhead
            self._play_timer.start()

    def _update_playhead(self) -> None:
        pos = self._player.position()
        self.set_cursor(pos)  # the cursor tracks playback progress
        self._follow(pos)

    def _follow(self, pos: float) -> None:
        """Page the view forward so the playhead stays visible during playback."""
        t0, t1 = self.visible_range()
        width = t1 - t0
        if width > 0 and (pos > t1 - 0.02 * width or pos < t0):
            lo = max(pos - 0.1 * width, 0.0)
            self.set_visible_range(lo, lo + width)

    def _on_playback_finished(self) -> None:
        self._play_timer.stop()
        self.set_cursor(self._player.position())  # leave the cursor exactly where playback stopped
        self._toolbar.set_playing(False)

    def _on_volume_changed(self, volume: float) -> None:
        self._player.set_volume(volume)

    def add_label_lane(self, name: str, editable: bool = False) -> LabelLane:
        display = _LANE_DISPLAY.get(name, name)
        plot = self._add_row(LABEL_LANE_HEIGHT, viewbox=InteractiveViewBox())
        plot.hideAxis("bottom")
        plot.setXLink(self._wave_plot)
        self._wire_vb(plot.getViewBox())
        self._header.add_lane(display, LABEL_LANE_HEIGHT, editable)  # left header row
        lane = LabelLane(plot, name, self._theme, editable=editable)
        lane.label_selected.connect(lambda iv, ln=lane: self._on_label_selected(ln, iv))
        if editable:
            lane.tier_changed.connect(self._record_history)
        self._label_lanes.append(lane)
        self._lane_plots.append(plot)
        self._add_mirror_region(plot)
        self._add_cursor_line(plot)
        if editable and self._focus_lane is None:
            self._focus_lane = lane
        self._sync_header_focus()
        return lane

    def clear_tiers(self) -> None:
        """Remove all label lanes and reset selection/trial state (for reopening on a new step)."""
        self.set_selection(None)
        for plot in self._lane_plots:
            self._glw.removeItem(plot)
        self._header.clear_lanes()
        self._label_lanes = []
        self._lane_plots = []
        self._focus_lane = None
        self._active_lane = None
        self._trial_index = None
        del self._sel_regions[1:]  # keep only the spectrogram mirror (added in __init__)
        del self._cursor_lines[1:]  # keep only the spectrogram cursor line
        self.set_cursor(None)
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
        self._undo_stack = [self._snapshot()]  # baseline state for undo
        self._undo_idx = 0
        self._clipboard = None

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
        self._glw.setBackground(theme.color("lane-bg"))  # the plot column surface
        self._header.apply_theme(theme)
        self._toolbar.set_theme_name(theme.name)
        self.waveform.apply_theme(theme)
        self.spectrogram.apply_theme(theme)
        for lane in self._label_lanes:
            lane.apply_theme(theme)
        self._restyle_overlays()

    def _restyle_overlays(self) -> None:
        accent = self._theme.color("accent")
        fill = QColor(accent)
        fill.setAlpha(40)
        for region in (self._sel_master, *self._sel_regions):
            region.setBrush(pg.mkBrush(fill))
            for line in region.lines:
                line.setPen(pg.mkPen(accent, width=1))
        dashed = pg.mkPen(accent, width=1, style=Qt.PenStyle.DashLine)
        for line in (self._cursor_master, *self._cursor_lines):
            line.setPen(dashed)

    def load(self, wav_path, cache_dir=None) -> None:
        self._player.stop()  # don't keep playing a previous file
        wav_path = Path(wav_path)
        self._wav_path = wav_path
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

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._player.stop()  # don't keep playing audio after the editor window closes
        super().closeEvent(event)

    # ---- keyboard editing ----
    def event(self, e) -> bool:  # noqa: N802 - Qt override
        # Intercept Tab/Shift+Tab before Qt's focus traversal so they navigate labels instead.
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._navigate(1 if e.key() == Qt.Key.Key_Tab else -1)
            return True
        return super().event(e)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        mods = event.modifiers()
        ctrl = mods & Qt.KeyboardModifier.ControlModifier
        shift = mods & Qt.KeyboardModifier.ShiftModifier
        if ctrl and key == Qt.Key.Key_S:
            self.save()
        elif ctrl and key == Qt.Key.Key_B:
            self._create_label_from_selection()
        elif ctrl and key == Qt.Key.Key_C:
            self._copy_active()
        elif ctrl and key == Qt.Key.Key_X:
            self._cut_active()
        elif ctrl and key == Qt.Key.Key_V:
            self._paste()
        elif ctrl and key == Qt.Key.Key_Z and not shift:
            self._undo()
        elif (ctrl and key == Qt.Key.Key_Y) or (ctrl and shift and key == Qt.Key.Key_Z):
            self._redo()
        elif key == Qt.Key.Key_Space:
            self._toggle_play()
        elif key == Qt.Key.Key_Escape:
            self.close()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._rename_active()
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
        self._sync_header_focus()

    def _sync_header_focus(self) -> None:
        """Highlight the header row of the active (or default editable) lane."""
        lane = self._active_lane or self._focus_lane
        idx = self._label_lanes.index(lane) if lane in self._label_lanes else -1
        self._header.set_focus(idx)

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
        # clicked an audio lane (waveform/spectrogram/ruler): drop a cursor, clear any selection
        self._select_only(None)
        self.set_selection(None)
        for plot in (self._wave_plot, self._spec_plot, self._ruler):
            vb = plot.getViewBox()
            if vb.sceneBoundingRect().contains(pos):
                x = float(vb.mapSceneToView(pos).x())
                self.set_cursor(x)
                if self._player.is_playing():  # clicking while playing seeks: continue from here
                    self._player.play(self._wav_path, x, None)
                return
        self.set_cursor(None)

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

    # ---- clipboard ----
    def _copy_active(self) -> None:
        iv = self._active_lane.active_interval() if self._active_lane else None
        if iv is not None:
            self._clipboard = Interval(iv.start, iv.end, iv.label)

    def _cut_active(self) -> None:
        lane = self._active_lane
        if lane is not None and lane.editable and lane.active_interval() is not None:
            self._copy_active()
            lane.delete_active()

    def _paste(self) -> None:
        """Paste the clipboard label into the editable tier at the cursor / selection / origin."""
        if self._clipboard is None or self._focus_lane is None:
            return
        span = self._sel.span()
        start = self._cursor if self._cursor is not None else (span[0] if span else None)
        if start is None:
            start = self._clipboard.start
        dur = self._clipboard.end - self._clipboard.start
        self._select_only(self._focus_lane)
        self._focus_lane.create(start, start + dur, self._clipboard.label)

    # ---- undo / redo (state-history of the editable tier) ----
    def _snapshot(self) -> list[Interval]:
        if self._focus_lane is None:
            return []
        return [Interval(iv.start, iv.end, iv.label) for iv in self._focus_lane.intervals()]

    def _record_history(self) -> None:
        if self._restoring or self._focus_lane is None:
            return
        snap = self._snapshot()
        if self._undo_stack and snap == self._undo_stack[self._undo_idx]:
            return  # no actual change
        del self._undo_stack[self._undo_idx + 1 :]  # drop the redo tail
        self._undo_stack.append(snap)
        self._undo_idx = len(self._undo_stack) - 1

    def _undo(self) -> None:
        if self._undo_idx > 0:
            self._undo_idx -= 1
            self._restore(self._undo_stack[self._undo_idx])

    def _redo(self) -> None:
        if self._undo_idx < len(self._undo_stack) - 1:
            self._undo_idx += 1
            self._restore(self._undo_stack[self._undo_idx])

    def _restore(self, snap: list[Interval]) -> None:
        if self._focus_lane is None:
            return
        self._restoring = True
        try:
            copy = [Interval(iv.start, iv.end, iv.label) for iv in snap]
            self._focus_lane.set_tier(Tier(self._focus_lane.name, copy))
        finally:
            self._restoring = False
        self._select_only(None)
        self.set_selection(None)

    def _center_on(self, a: float, b: float) -> None:
        """Scroll the view to show [a, b] (keeping the current zoom width) if it's off-screen."""
        t0, t1 = self.visible_range()
        if t0 <= a and b <= t1:
            return
        width = max(t1 - t0, b - a)
        centre = (a + b) / 2.0
        self.set_visible_range(max(centre - width / 2.0, 0.0), centre + width / 2.0)

    # ---- selection ----
    def _on_region_dragged(self, x_down: float, x_now: float, is_start: bool) -> None:
        """Drag inside the current selection moves it; drag outside makes a new selection."""
        if is_start:
            span = self._sel.span()
            if span is not None and span[0] <= x_down <= span[1]:
                self._drag_mode = "move"
                self._drag_anchor = span
            else:
                self._drag_mode = "new"
                self._drag_anchor = None
                self._select_only(None)  # a fresh time-drag clears any selected label
                self.set_cursor(None)
        if self._drag_mode == "move" and self._drag_anchor is not None:
            a, b = self._drag_anchor
            width = b - a
            lo = a + (x_now - x_down)
            lo = max(lo, 0.0)
            if self._duration:
                lo = min(lo, self._duration - width)
            self.set_selection((lo, lo + width))
        else:
            self.set_selection((min(x_down, x_now), max(x_down, x_now)))

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
        if span is not None:
            self.set_cursor(None)  # a span supersedes the click cursor
            if self._trial_index is not None:
                mid = (span[0] + span[1]) / 2.0
                self._trial_panel.set_trial(self._trial_index.at(mid))
        else:
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
