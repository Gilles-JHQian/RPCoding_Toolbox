"""A small frameless loading dialog with a progress bar (app startup + editor open)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QProgressBar, QVBoxLayout


class LoadingDialog(QDialog):
    """A compact, frameless, always-on-top progress popup. Uses the app's ``Panel`` styling."""

    def __init__(self, title: str = "Loading…", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        self.setFixedWidth(340)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("Panel")
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(11)

        self._title = QLabel(title)
        self._title.setObjectName("SectionTitle")
        lay.addWidget(self._title)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        lay.addWidget(self._bar)
        self._status = QLabel("")
        self._status.setObjectName("Meta")
        lay.addWidget(self._status)

    def set_progress(self, pct: int, message: str = "") -> None:
        self._bar.setRange(0, 100)
        self._bar.setValue(max(0, min(100, int(pct))))
        if message:
            self._status.setText(message)

    def set_busy(self, message: str = "") -> None:
        """Indeterminate (animated) bar for work with no measurable progress."""
        self._bar.setRange(0, 0)
        if message:
            self._status.setText(message)

    def show_centered(self) -> None:
        """Center over the parent window (or the screen) and show on top."""
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            center = parent.frameGeometry().center()
        else:
            center = QGuiApplication.primaryScreen().availableGeometry().center()
        geo = self.frameGeometry()
        geo.moveCenter(center)
        self.move(geo.topLeft())
        self.show()
        self.raise_()
