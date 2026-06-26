"""A read-only viewer for a run log (e.g. the MFA pipeline's ``mfa_run.log``)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class LogDialog(QDialog):
    """Show ``text`` read-only, scrolled to the end (where errors land). If ``folder`` is given, an
    'Open folder' button reveals it in the OS file manager."""

    def __init__(self, title: str, text: str, *, folder: Path | str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 540)
        self._folder = Path(folder) if folder else None

        lay = QVBoxLayout(self)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlainText(text)
        self._log.moveCursor(QTextCursor.MoveOperation.End)  # jump to the latest output
        lay.addWidget(self._log, 1)

        row = QHBoxLayout()
        if self._folder is not None:
            open_btn = QPushButton("📂 Open folder")
            open_btn.setToolTip(str(self._folder))
            open_btn.clicked.connect(self._open_folder)
            row.addWidget(open_btn)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _open_folder(self) -> None:
        if self._folder is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder)))
