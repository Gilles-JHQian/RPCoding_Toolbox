"""Fix trigger misalignment gadget (Settings → Anomaly handling → Fix trigger misalignment).

Pick a subject whose ``Trials.Auditory`` is corrupted by a mis-counted trigger; the dialog detects
the raw ``trigger.mat`` pulses (threshold adjustable — the one genuinely per-subject step, mirroring
``maketrigtimes``), aligns them to ``trialInfo`` via
:func:`rpcoding.core.trigger_fix.align_to_trialinfo`, and shows the before/after per-block residual
over the waveform so you can confirm before applying. Apply writes the corrected ``Auditory`` back
into the D_Data ``Trials.mat`` (original backed up) and regenerates the cue/condition events.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.matio import load_trialinfo, load_trials, trial_audio_onset
from rpcoding.core.retry import retry_transient_io
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.tasks import Task
from rpcoding.core.trials_combine import resolve_trials_mat
from rpcoding.core.trigger_fix import (
    EDF_RATE,
    _block_index,
    _residuals,
    align_to_trialinfo,
    apply_trigger_fix,
    auto_threshold,
    detect_pulses,
    find_trigger_mat,
    is_improvement,
    read_freq,
    read_trigger,
)
from rpcoding.gui.theme import DARK_THEME, Theme

_ENVELOPE_BINS = 4000  # max-pooled display points for the whole-recording waveform


@dataclass
class _Loaded:
    """Everything loaded once per subject, so threshold tweaks re-detect without re-reading Box."""

    trigger: np.ndarray
    freq: float
    audio: np.ndarray
    blocks: np.ndarray
    results_dir: object
    d_data_dir: object
    trials_mat: object
    before_max_ms: float | None
    before_blocks: list | None  # per-block residual of the current Trials.Auditory (None if unread)
    env_x: np.ndarray
    env_y: np.ndarray


class TriggerFixDialog(QDialog):
    """Detect + align a subject's stimulus triggers to trialInfo, review, and apply the fix."""

    def __init__(
        self,
        config: AppConfig,
        default_task: Task | None = None,
        default_subject: str | None = None,
        theme: Theme | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._theme = theme or DARK_THEME
        self._loaded: _Loaded | None = None
        self.setWindowTitle("Fix trigger misalignment")
        self.resize(760, 640)

        outer = QVBoxLayout(self)
        outer.addWidget(
            QLabel(
                "Re-derive a subject's stimulus triggers from the raw trigger.mat, guided by\n"
                "trialInfo. Adjust the detection threshold if needed, check the before/after\n"
                "residual, then apply — it writes a corrected Trials.mat and regenerates events."
            )
        )

        form = QFormLayout()
        outer.addLayout(form)
        self._task = QComboBox()
        for t in Task:
            self._task.addItem(t.value, t)
        if default_task is not None:
            self._task.setCurrentIndex(self._task.findData(default_task))
        self._task.currentIndexChanged.connect(lambda: self._reload_subjects())
        form.addRow("Task", self._task)
        self._subject = QComboBox()
        self._subject.currentIndexChanged.connect(self._on_subject_changed)
        form.addRow("Subject", self._subject)

        # threshold control (fraction between baseline and peak; the per-subject knob)
        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("Detection threshold"))
        self._thr = QSlider(Qt.Orientation.Horizontal)
        self._thr.setRange(5, 95)
        self._thr.setValue(40)  # matches core auto_threshold default (0.40)
        self._thr.setEnabled(False)
        self._thr.valueChanged.connect(self._on_threshold_changed)
        thr_row.addWidget(self._thr, 1)
        self._thr_label = QLabel("—")
        self._thr_label.setMinimumWidth(220)
        thr_row.addWidget(self._thr_label)
        outer.addLayout(thr_row)

        self._plot = pg.PlotWidget()
        self._plot.setMinimumHeight(230)
        self._plot.setMouseEnabled(x=True, y=False)
        self._plot.setLabel("bottom", "EDF time", units="s")
        self._plot.getPlotItem().hideButtons()
        self._plot.setBackground(self._theme.color("lane-bg"))
        outer.addWidget(self._plot, 1)

        self._out = QPlainTextEdit()
        self._out.setReadOnly(True)
        self._out.setObjectName("Mono")
        self._out.setMinimumHeight(120)
        outer.addWidget(self._out)

        row = QHBoxLayout()
        self._analyze = QPushButton("Analyze")
        self._analyze.setObjectName("Primary")
        self._analyze.clicked.connect(self._do_analyze)
        row.addWidget(self._analyze)
        self._apply = QPushButton("Apply fix")
        self._apply.setEnabled(False)
        self._apply.clicked.connect(self._do_apply)
        row.addWidget(self._apply)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

        self._reload_subjects(default_subject)

    # ---- subject selection ----
    def _current_task(self) -> Task:
        t = self._task.currentData()
        return t if isinstance(t, Task) else Task.from_str(str(t))

    def _reload_subjects(self, default_subject: str | None = None) -> None:
        self._subject.blockSignals(True)
        self._subject.clear()
        subs = scan_subjects(paths.d_data_dir(self._config.droot, self._current_task()))
        self._subject.addItems(subs)
        if default_subject and default_subject in subs:
            self._subject.setCurrentText(default_subject)
        if not subs:
            self._subject.addItem("(no subjects found)")
        self._subject.blockSignals(False)
        self._analyze.setEnabled(bool(subs))
        self._on_subject_changed()

    def _on_subject_changed(self) -> None:
        self._loaded = None
        self._thr.setEnabled(False)
        self._apply.setEnabled(False)
        self._plot.clear()
        self._out.setPlainText("")

    # ---- analyze (load once, then detect + align) ----
    def _do_analyze(self) -> None:
        self._out.setPlainText("Loading trigger.mat + trialInfo …")
        QApplication.processEvents()
        try:
            self._loaded = self._load()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._loaded = None
            self._out.setPlainText(f"Error: {type(exc).__name__}: {exc}")
            return
        self._thr.setEnabled(True)
        self._refresh()

    def _load(self) -> _Loaded:
        task, subj = self._current_task(), self._subject.currentText()
        droot = self._config.droot
        results_dir = paths.results_dir(droot, task, subj)
        d_data_dir = paths.d_data_subject_dir(droot, task, subj)
        trialinfo = load_trialinfo(results_dir / paths.TRIALINFO_MAT)
        audio = np.array([float(trial_audio_onset(ti)) for ti in trialinfo])
        blocks = _block_index(trialinfo)

        trials_mat = resolve_trials_mat(d_data_dir, results_dir).path
        before_max, before_blocks = None, None
        try:
            trials = load_trials(trials_mat)
            if len(trials) == len(trialinfo):
                cur = np.array([float(tr["Auditory"]) / EDF_RATE for tr in trials])
                before_blocks = _residuals(cur, audio, blocks)
                before_max = max(b.residual_ms for b in before_blocks)
        except (KeyError, ValueError, OSError):
            before_max, before_blocks = None, None

        trig_path = find_trigger_mat(d_data_dir)
        freq = read_freq(trig_path)
        trigger = retry_transient_io(lambda: read_trigger(trig_path))
        env_x, env_y = _envelope(trigger, freq)
        return _Loaded(trigger, freq, audio, blocks, results_dir, d_data_dir, trials_mat,
                       before_max, before_blocks, env_x, env_y)

    def _threshold(self) -> float:
        return auto_threshold(self._loaded.trigger, self._thr.value() / 100.0)

    def _on_threshold_changed(self) -> None:
        if self._loaded is not None:
            self._refresh()

    def _refresh(self) -> None:
        ld = self._loaded
        level = self._threshold()
        pulses = detect_pulses(ld.trigger, ld.freq, level)
        res = align_to_trialinfo(pulses, ld.audio, ld.blocks)
        improved = is_improvement(res, ld.before_max_ms)
        self._thr_label.setText(
            f"frac {self._thr.value() / 100:.2f} → {level:,.0f}  ·  {len(pulses)} pulses"
        )
        self._draw(level, pulses, res.corrected_sec)
        self._report(res, ld.before_max_ms, len(pulses), improved)
        self._apply.setEnabled(bool(improved))

    # ---- rendering ----
    def _draw(self, level: float, pulses: np.ndarray, corrected: np.ndarray) -> None:
        ld = self._loaded
        self._plot.clear()
        base = float(np.median(ld.trigger))
        peak = float(ld.env_y.max())
        span = max(peak - base, 1.0)
        self._plot.plot(ld.env_x, ld.env_y, pen=pg.mkPen(self._theme.color("wave-stroke"), width=1))
        self._plot.addLine(y=level, pen=pg.mkPen(self._theme.color("accent"), width=1,
                                                 style=Qt.PenStyle.DashLine))
        # pulse rug (top) + recovered trial rug (bottom)
        self._rug(pulses, peak + 0.10 * span, "#39d98a")  # green: detected pulses
        self._rug(corrected, base - 0.12 * span, self._theme.color("accent"))  # recovered trials
        self._plot.setYRange(base - 0.22 * span, peak + 0.20 * span, padding=0)

    def _rug(self, xs: np.ndarray, y: float, color: str) -> None:
        if len(xs) == 0:
            return
        self._plot.addItem(
            pg.ScatterPlotItem(
                xs, np.full(len(xs), y), symbol="|", size=9, pen=pg.mkPen(color, width=1),
                brush=None,
            )
        )

    def _report(self, res, before: float | None, n_pulses: int, improved: bool) -> None:
        ld = self._loaded
        lines = [
            f"{self._current_task().value} / {self._subject.currentText()}",
            f"pulses detected: {n_pulses}    trials: {len(ld.audio)}    "
            f"template hits: {res.template_hits}    snapped: {res.n_matched}",
            "",
            f"  {'block':>5} {'trials':>6} {'matched':>7} {'before(ms)':>11} {'after(ms)':>10}",
        ]
        before_blocks = ld.before_blocks
        for i, b in enumerate(res.blocks):
            bstr = f"{before_blocks[i].residual_ms:>11.0f}" if before_blocks else f"{'—':>11}"
            flag = "OK" if b.aligned else "MISALIGNED"
            lines.append(f"  {b.block:>5} {b.n_trials:>6} {b.n_matched:>7} {bstr} "
                         f"{b.residual_ms:>10.0f}  {flag}")
        lines.append("")
        before_str = f"{before:.0f} ms" if before is not None else "unknown"
        verdict = (
            "✓ aligned — better than the current data; safe to apply."
            if improved
            else ("current data is already at least this good — leave it as-is."
                  if res.aligned else "could not align (check the threshold / pulse structure).")
        )
        lines.append(f"current (before): {before_str}    re-derived (after): "
                     f"{res.max_residual_ms:.0f} ms")
        lines.append(verdict)
        self._out.setPlainText("\n".join(lines))

    # ---- apply ----
    def _do_apply(self) -> None:
        ld = self._loaded
        task, subj = self._current_task(), self._subject.currentText()
        if QMessageBox.question(
            self, "Apply trigger fix",
            f"Write the corrected Auditory back into the D_Data Trials.mat and regenerate\n"
            f"cue/condition events for {task.value} / {subj}?\n\n"
            f"The originals are backed up (*.before_trigger_fix).",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._out.appendPlainText("\nApplying …")
        QApplication.processEvents()
        try:
            report = retry_transient_io(
                lambda: apply_trigger_fix(
                    ld.results_dir, ld.d_data_dir, ld.trials_mat, thresh=self._threshold()
                )
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._out.appendPlainText(f"Error: {type(exc).__name__}: {exc}")
            return
        self._out.appendPlainText(
            f"✓ corrected Auditory in D_Data {report.trials_path.name} "
            f"(residual {report.align.max_residual_ms:.0f} ms); "
            f"events regenerated: {report.events_regenerated}.\n"
            f"Downstream steps (write-Trials, events.tsv) will now read the corrected Trials.mat."
        )
        self._apply.setEnabled(False)  # applied; re-analyze to act again


def _envelope(trigger: np.ndarray, freq: float) -> tuple[np.ndarray, np.ndarray]:
    """Max-pool the whole trigger channel to ~_ENVELOPE_BINS points so pulses survive as spikes."""
    n = len(trigger)
    if n == 0:
        return np.zeros(0), np.zeros(0)
    w = max(n // _ENVELOPE_BINS, 1)
    bins = n // w
    pooled = trigger[: bins * w].reshape(bins, w).max(axis=1)
    x = (np.arange(bins) * w + w / 2) / freq
    return x, pooled.astype(np.float64)
