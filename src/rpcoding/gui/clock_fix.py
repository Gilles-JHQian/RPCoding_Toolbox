"""Subject picker for the clock-drift fix gadget (Settings → Anomaly handling → Fix clock drift).

The dialog only chooses *which* subject to mark; the marking itself happens in the audio editor
(opened by the dashboard) on a dedicated ``clock_anchors`` lane. See
:func:`rpcoding.gui.editor_loader.tiers_for_clock_anchors`.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.tasks import Task


class ClockFixDialog(QDialog):
    """Pick a task + subject to mark clock-drift anchors for."""

    def __init__(self, config: AppConfig, default_task: Task | None = None, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Fix clock drift — pick a subject")
        self.resize(420, 200)

        outer = QVBoxLayout(self)
        outer.addWidget(
            QLabel(
                "Mark the true stimulus position of each block's first and last trial (and any\n"
                "anomalous trials) on the audio. These anchors fit the EDF-vs-audio clock drift."
            )
        )
        form = QFormLayout()
        outer.addLayout(form)

        self._task = QComboBox()
        for t in Task:
            self._task.addItem(t.value, t)
        if default_task is not None:
            self._task.setCurrentIndex(self._task.findData(default_task))
        self._task.currentIndexChanged.connect(self._reload_subjects)
        form.addRow("Task", self._task)

        self._subject = QComboBox()
        form.addRow("Subject", self._subject)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._reload_subjects()

    def _reload_subjects(self) -> None:
        self._subject.clear()
        subs = scan_subjects(paths.d_data_dir(self._config.droot, self.task))
        self._subject.addItems(subs)
        ok = bool(subs)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        if not ok:
            self._subject.addItem("(no subjects found)")

    @property
    def task(self) -> Task:
        return self._task.currentData()

    @property
    def subject(self) -> str:
        return self._subject.currentText()
