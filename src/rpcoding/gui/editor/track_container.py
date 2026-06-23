"""AudioEditor: stacked waveform + spectrogram (+ label lanes) on one shared time axis."""

from __future__ import annotations

from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from rpcoding.core.audio.io import duration_seconds
from rpcoding.core.audio.render.cache import AudioRenderCache
from rpcoding.gui.editor.debounce import RangeDebouncer
from rpcoding.gui.editor.label_lane import LabelLane
from rpcoding.gui.editor.render_jobs import build_pyramid_job, build_spectrogram_job
from rpcoding.gui.editor.spectrogram_lane import SpectrogramLane
from rpcoding.gui.editor.toolbar import EditorToolbar
from rpcoding.gui.editor.waveform_lane import WaveformLane
from rpcoding.gui.theme import DARK_THEME, Theme
from rpcoding.gui.workers.worker import run_in_thread

pg.setConfigOptions(imageAxisOrder="row-major")

_LEFT_W = 64
_RULER_H = 26
_LANE_H = 132
_LABEL_H = 40


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

    def __init__(self, theme: Theme = DARK_THEME, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._duration = 0.0
        self._load_token = 0
        self._pyr_ok = False
        self._spec_ok = False
        self._jobs: list = []
        self._label_lanes: list[LabelLane] = []
        self._row = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._toolbar = EditorToolbar()
        self._toolbar.amplitude_changed.connect(self.set_amplitude_scale)
        lay.addWidget(self._toolbar)
        self._glw = pg.GraphicsLayoutWidget()
        lay.addWidget(self._glw, 1)

        self._ruler = self._add_plot(_RULER_H, axis={"bottom": TimeAxisItem(orientation="bottom")})
        self._ruler.hideAxis("left")

        self._wave_plot = self._add_plot(_LANE_H)
        self._wave_plot.hideAxis("bottom")
        self._owner_vb = self._wave_plot.getViewBox()
        self._owner_vb.setMouseEnabled(x=True, y=False)
        self.waveform = WaveformLane(self._wave_plot, theme)

        self._spec_plot = self._add_plot(_LANE_H)
        self._spec_plot.hideAxis("bottom")
        self._hist = pg.HistogramLUTItem()
        self._glw.addItem(self._hist, row=self._row - 1, col=1)
        self.spectrogram = SpectrogramLane(self._spec_plot, self._hist, theme)

        # Link every non-owner lane's X to the waveform; only the owner drives pan/zoom.
        for plot in (self._ruler, self._spec_plot):
            plot.setXLink(self._wave_plot)
            plot.getViewBox().setMouseEnabled(x=False, y=False)

        self._debouncer = RangeDebouncer(40, self)
        self._debouncer.flushed.connect(self._reslice_all)
        self._owner_vb.sigXRangeChanged.connect(self._on_x_range)

    # ---- layout helper ----
    def _add_plot(self, height: int, axis: dict | None = None) -> pg.PlotItem:
        plot = self._glw.addPlot(row=self._row, col=0, axisItems=axis or {})
        self._row += 1
        plot.setMinimumHeight(height)
        plot.setMaximumHeight(height)
        plot.getAxis("left").setWidth(_LEFT_W)
        plot.getViewBox().setMenuEnabled(False)
        return plot

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

    def set_db_range(self, lo: float, hi: float) -> None:
        self.spectrogram.set_db_levels(lo, hi)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.waveform.apply_theme(theme)
        self.spectrogram.apply_theme(theme)
        for lane in self._label_lanes:
            lane.apply_theme(theme)

    def add_label_lane(self, name: str) -> LabelLane:
        plot = self._add_plot(_LABEL_H)
        plot.hideAxis("bottom")
        plot.setXLink(self._wave_plot)
        plot.getViewBox().setMouseEnabled(x=False, y=False)
        lane = LabelLane(plot, name, self._theme)
        self._label_lanes.append(lane)
        return lane

    def load(self, wav_path, cache_dir=None) -> None:
        wav_path = Path(wav_path)
        self._duration = duration_seconds(wav_path)
        self.set_visible_range(0.0, self._duration)
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
                on_result=lambda pyr, tk=token, w=wav_path: self._on_pyramid(tk, pyr, w),
                on_error=lambda msg: self.load_failed.emit(msg),
            )
        )
        self._jobs.append(
            run_in_thread(
                self,
                build_spectrogram_job,
                wav_path,
                cache_root,
                content_key,
                on_result=lambda handle, tk=token: self._on_spectro(tk, handle),
                on_error=lambda msg: self.load_failed.emit(msg),
            )
        )

    def clear(self) -> None:
        self.spectrogram.close_source()

    # ---- internals ----
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
