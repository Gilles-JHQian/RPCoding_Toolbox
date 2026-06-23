"""Batch dialog: run the automated pipeline for many subjects with aggregated progress.

``run_batch`` runs on a worker thread; its per-subject ``on_progress`` callback (called off the UI
thread) emits a Qt signal, so the table updates safely on the UI thread (queued connection).
"""

from __future__ import annotations

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


class _Relay(QObject):
    """Marshals worker-thread progress onto the UI thread."""

    subject_done = Signal(str, str, str)  # subject, status ("ok"/"error"), detail


class BatchDialog(QDialog):
    def __init__(self, config: AppConfig, task: Task, subjects: Sequence[str], parent=None):
        super().__init__(parent)
        self._config = config
        self._task = task
        self._subjects = list(subjects)
        self._active: tuple | None = None
        self.setWindowTitle(f"Batch — {task.value}")
        self.resize(560, 420)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{len(self._subjects)} subject(s) · automated steps only"))

        self._table = QTableWidget(len(self._subjects), 2)
        self._table.setHorizontalHeaderLabels(["Subject", "Status"])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._rows: dict[str, int] = {}
        for i, subj in enumerate(self._subjects):
            self._table.setItem(i, 0, QTableWidgetItem(subj))
            self._table.setItem(i, 1, QTableWidgetItem("Queued"))
            self._rows[subj] = i
        lay.addWidget(self._table, 1)

        self._bar = QProgressBar()
        self._bar.setRange(0, max(len(self._subjects), 1))
        self._bar.setValue(0)
        lay.addWidget(self._bar)

        row = QHBoxLayout()
        row.addStretch(1)
        self._run = QPushButton("Run")
        self._run.setObjectName("Primary")
        self._run.clicked.connect(self._start)
        row.addWidget(self._run)
        self._close = QPushButton("Close")
        self._close.clicked.connect(self.reject)
        row.addWidget(self._close)
        lay.addLayout(row)

        self._relay = _Relay()
        self._relay.subject_done.connect(self._on_subject_done)
        self._completed = 0

    def _start(self) -> None:
        if not self._subjects:
            return
        self._run.setEnabled(False)
        self._completed = 0
        self._bar.setValue(0)

        def on_progress(subject: str, result: tuple) -> None:
            status, detail = result
            self._relay.subject_done.emit(subject, status, str(detail))

        self._active = run_in_thread(
            self,
            run_batch,
            self._config,
            self._task,
            self._subjects,
            on_progress=on_progress,
            on_finished=self._on_finished,
        )

    def _on_subject_done(self, subject: str, status: str, detail: str) -> None:
        row = self._rows.get(subject)
        if row is None:
            return
        text = "✓ ran" if status == "ok" else f"✗ {detail}"
        self._table.setItem(row, 1, QTableWidgetItem(text))
        self._completed += 1
        self._bar.setValue(self._completed)

    def _on_finished(self) -> None:
        self._run.setEnabled(True)
        self._bar.setValue(self._bar.maximum())
