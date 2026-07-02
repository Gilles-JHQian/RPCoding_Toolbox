"""Merge multi-part recording files gadget (Settings → Anomaly handling → Merge multi-part files).

Pick a subject; if its D_Data has numbered parts (Trials1/Trials2, trialInfo1/2, experiment1/2),
combine them into single Trials.mat / trialInfo.mat / experiment.mat in that subject's D_Data folder
(see :func:`rpcoding.core.multipart.merge_subject`). Existing merged files are never overwritten.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.multipart import merge_subject
from rpcoding.core.retry import retry_transient_io
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.tasks import Task


class MergeMultipartDialog(QDialog):
    """Pick a subject and merge its numbered multi-part files into single files in D_Data."""

    def __init__(
        self,
        config: AppConfig,
        default_task: Task | None = None,
        default_subject: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Merge multi-part recording files")
        self.resize(560, 400)

        outer = QVBoxLayout(self)
        outer.addWidget(
            QLabel(
                "For a subject recorded in more than one part, combine the numbered parts\n"
                "(Trials1/2, trialInfo1/2, experiment1/2) into single Trials.mat / trialInfo.mat\n"
                "/ experiment.mat in D_Data. Existing merged files are not overwritten."
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
        form.addRow("Subject", self._subject)

        self._out = QPlainTextEdit()
        self._out.setReadOnly(True)
        self._out.setObjectName("Mono")
        outer.addWidget(self._out, 1)

        row = QHBoxLayout()
        self._merge = QPushButton("Merge")
        self._merge.setObjectName("Primary")
        self._merge.clicked.connect(self._do_merge)
        row.addWidget(self._merge)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        outer.addLayout(row)

        self._reload_subjects(default_subject)

    def _current_task(self) -> Task:
        # Qt stores a StrEnum userData as a plain str; normalise back to a Task.
        t = self._task.currentData()
        return t if isinstance(t, Task) else Task.from_str(str(t))

    def _reload_subjects(self, default_subject: str | None = None) -> None:
        self._subject.clear()
        subs = scan_subjects(paths.d_data_dir(self._config.droot, self._current_task()))
        self._subject.addItems(subs)
        if default_subject and default_subject in subs:
            self._subject.setCurrentText(default_subject)
        self._merge.setEnabled(bool(subs))
        if not subs:
            self._subject.addItem("(no subjects found)")

    def _do_merge(self) -> None:
        subj = self._subject.currentText()
        task = self._current_task()
        d_dir = paths.d_data_subject_dir(self._config.droot, task, subj)
        self._out.setPlainText(f"Merging {task.value} / {subj} …")
        QApplication.processEvents()  # show the "merging" line before the (possibly slow) Box IO
        try:
            results = retry_transient_io(lambda: merge_subject(d_dir))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._out.setPlainText(f"Error: {type(exc).__name__}: {exc}")
            return
        lines = [f"{task.value} / {subj}", str(d_dir), ""]
        for r in results:
            lines.append(f"  {r.name:<15}{r.status:<13}{r.detail}")
        if not any(r.status == "merged" for r in results):
            lines += ["", "Nothing to merge (no numbered parts, or already merged)."]
        self._out.setPlainText("\n".join(lines))
