"""A step-runner dialog: title, progress bar, live log, and a close/cancel button."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ProgressDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 360)
        self._done = False

        lay = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 600;")
        lay.addWidget(heading)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate until finished
        lay.addWidget(self._bar)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        lay.addWidget(self._log, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        self._btn = QPushButton("Cancel")
        self._btn.clicked.connect(self.reject)
        row.addWidget(self._btn)
        lay.addLayout(row)

    def append(self, line: str) -> None:
        self._log.appendPlainText(line)

    def finish(self, ok: bool, message: str = "") -> None:
        self._done = True
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        if message:
            self.append(message)
        self._btn.setText("Close")
        self._btn.clicked.disconnect()
        self._btn.clicked.connect(self.accept)
