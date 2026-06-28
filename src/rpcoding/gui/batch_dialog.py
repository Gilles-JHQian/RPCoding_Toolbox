"""Batch dialog: run the automated pipeline for many subjects with detailed progress.

``run_batch`` runs on a worker thread; its ``on_step`` / ``on_progress`` callbacks (called off the
UI thread) emit Qt signals via a relay, so the table + bars update safely on the UI thread.
Each subject row shows the current step and a per-step bar; the footer bar shows overall progress.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from rpcoding.core.config import AppConfig
from rpcoding.core.runner import run_batch
from rpcoding.core.tasks import Task
from rpcoding.gui.workers.worker import run_in_thread

_OVERALL_SCALE = 1000  # fine-grained footer bar so fractional subject progress shows smoothly


class _Relay(QObject):
    """Marshals worker-thread progress onto the UI thread."""

    subject_done = Signal(str, str, str)  # subject, status ("ok"/"error"), detail
    step_tick = Signal(str, str, object, str, float)  # subject, title, fraction|None, msg, overall


class BatchDialog(QDialog):
    def __init__(self, config: AppConfig, task: Task, subjects: Sequence[str], parent=None):
        super().__init__(parent)
        self._config = config
        self._task = task
        self._subjects = list(subjects)
        self._active: tuple | None = None
        self.setWindowTitle(f"Batch — {task.value}")
        self.resize(640, 460)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{len(self._subjects)} subject(s) · automated steps only"))

        self._table = QTableWidget(len(self._subjects), 3)
        self._table.setHorizontalHeaderLabels(["Subject", "Current step", "Progress"])
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 90)
        self._table.setColumnWidth(2, 170)
        self._rows: dict[str, int] = {}
        self._bars: dict[str, QProgressBar] = {}
        for i, subj in enumerate(self._subjects):
            self._table.setItem(i, 0, QTableWidgetItem(subj))
            self._table.setItem(i, 1, QTableWidgetItem("Queued"))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            self._table.setCellWidget(i, 2, bar)
            self._rows[subj] = i
            self._bars[subj] = bar
        lay.addWidget(self._table, 1)

        foot = QHBoxLayout()
        self._overall_label = QLabel("Ready")
        self._overall_label.setObjectName("Meta")
        foot.addWidget(self._overall_label)
        foot.addStretch(1)
        lay.addLayout(foot)

        self._bar = QProgressBar()
        self._bar.setRange(0, _OVERALL_SCALE)
        self._bar.setValue(0)
        self._bar.setFormat("%p%")
        lay.addWidget(self._bar)

        row = QHBoxLayout()
        row.addStretch(1)
        self._run = QPushButton("Run")
        self._run.setObjectName("Primary")
        self._run.clicked.connect(self._start)
        row.addWidget(self._run)
        self._stop = QPushButton("Stop")
        self._stop.setEnabled(False)
        self._stop.clicked.connect(self._request_stop)
        row.addWidget(self._stop)
        self._close = QPushButton("Close")
        self._close.clicked.connect(self.reject)
        row.addWidget(self._close)
        lay.addLayout(row)

        self._relay = _Relay()
        self._relay.subject_done.connect(self._on_subject_done)
        self._relay.step_tick.connect(self._on_step_tick)
        self._completed = 0
        # Set from the UI thread, polled from the worker thread (threading.Event is thread-safe).
        self._cancel = threading.Event()
        self._running = False

    def _start(self) -> None:
        if not self._subjects or self._running:
            return
        self._running = True
        self._cancel.clear()
        self._run.setEnabled(False)
        self._stop.setEnabled(True)
        self._completed = 0
        self._bar.setValue(0)
        self._overall_label.setText(f"Running 0 / {len(self._subjects)} subjects…")

        def on_progress(subject: str, result: tuple) -> None:
            status, detail = result
            self._relay.subject_done.emit(subject, status, str(detail))

        def on_step(subject: str, sp) -> None:  # sp: StepProgress
            self._relay.step_tick.emit(subject, sp.title, sp.fraction, sp.message, sp.overall)

        self._active = run_in_thread(
            self,
            run_batch,
            self._config,
            self._task,
            self._subjects,
            on_progress=on_progress,
            on_step=on_step,
            should_cancel=self._cancel.is_set,
            on_finished=self._on_finished,
        )

    def _request_stop(self) -> None:
        """Ask the batch to stop after the in-flight step finishes (cooperative cancel)."""
        if not self._running:
            return
        self._cancel.set()
        self._stop.setEnabled(False)
        self._overall_label.setText("Stopping after the current step…")

    def _on_step_tick(
        self, subject: str, title: str, fraction: float | None, message: str, overall: float
    ) -> None:
        row = self._rows.get(subject)
        if row is None:
            return
        phase = f"{title} — {message}" if message else title
        self._table.setItem(row, 1, QTableWidgetItem(phase[:80]))
        bar = self._bars[subject]
        if fraction is None:
            bar.setRange(0, 0)  # busy / indeterminate
        else:
            bar.setRange(0, 100)
            bar.setValue(0 if fraction < 0 else 100 if fraction > 1 else int(round(fraction * 100)))
        # Footer: subjects fully done + this subject's within-pipeline fraction.
        total = max(len(self._subjects), 1)
        self._bar.setValue(int(round((self._completed + overall) / total * _OVERALL_SCALE)))

    def _on_subject_done(self, subject: str, status: str, detail: str) -> None:
        row = self._rows.get(subject)
        if row is None:
            return
        text = "✓ ran" if status == "ok" else f"✗ {detail}"
        self._table.setItem(row, 1, QTableWidgetItem(text[:80]))
        bar = self._bars[subject]
        bar.setRange(0, 100)
        bar.setValue(100 if status == "ok" else bar.value())
        self._completed += 1
        n = len(self._subjects)
        self._bar.setValue(int(round(self._completed / max(n, 1) * _OVERALL_SCALE)))
        self._overall_label.setText(f"Running {self._completed} / {n} subjects…")

    def _on_finished(self) -> None:
        self._running = False
        self._run.setEnabled(True)
        self._stop.setEnabled(False)
        n = len(self._subjects)
        if self._cancel.is_set():
            for row in self._rows.values():
                if self._table.item(row, 1) and self._table.item(row, 1).text() == "Queued":
                    self._table.setItem(row, 1, QTableWidgetItem("— stopped"))
            self._overall_label.setText(f"Stopped · {self._completed} / {n} subjects ran")
        else:
            self._bar.setValue(_OVERALL_SCALE)
            self._overall_label.setText(f"Done · {self._completed} / {n} subjects")

    def reject(self) -> None:  # noqa: D102 - Qt override: closing a running batch cancels it
        if self._running:
            self._cancel.set()
        super().reject()
