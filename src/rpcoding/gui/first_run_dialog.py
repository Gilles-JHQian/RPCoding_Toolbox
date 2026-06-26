"""First-run dialog: explain which folder to pick, then let the user browse to it.

Popping a bare folder picker on first launch is confusing — the user doesn't know what they're
selecting. This shows an explanation and a Choose-folder button instead.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

# Subdirectories that mark a real CoganLab data root (used only for a soft "looks wrong" hint).
_EXPECTED = ("D_Data", "ECoG_Task_Data")


class DataRootDialog(QDialog):
    """Asks the user to pick the CoganLab data root, explaining what it is first."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to RPCoding Toolbox")
        self.setMinimumWidth(460)
        self._path: Path | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("Panel")
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(13)

        title = QLabel("Select your CoganLab data root")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)

        body = QLabel(
            "RPCoding Toolbox needs the folder that holds the lab's data — the one that contains "
            "<b>D_Data</b>, <b>ECoG_Task_Data</b>, etc. This is usually the <b>CoganLab</b> folder "
            "inside your Box drive (for example <code>…/Box/CoganLab</code>).<br><br>"
            "Click <b>Choose folder…</b> and select it. You can change this later in Settings."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(body)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._browse = QPushButton("Choose folder…")
        self._browse.setObjectName("Primary")
        self._browse.clicked.connect(self._choose)
        row.addWidget(self._browse)
        self._path_label = QLabel("No folder selected")
        self._path_label.setObjectName("SubPath")
        self._path_label.setWordWrap(True)
        row.addWidget(self._path_label, 1)
        lay.addLayout(row)

        self._hint = QLabel("")
        self._hint.setObjectName("Hint")
        self._hint.setWordWrap(True)
        self._hint.setVisible(False)
        lay.addWidget(self._hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self._ok = QPushButton("Open")
        self._ok.setObjectName("Primary")
        self._ok.setEnabled(False)
        self._ok.clicked.connect(self.accept)
        buttons.addWidget(self._ok)
        lay.addLayout(buttons)

    def _choose(self) -> None:
        start = str(self._path) if self._path else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select your CoganLab data root", start)
        if not chosen:
            return
        self._path = Path(chosen)
        self._path_label.setText(str(self._path))
        self._ok.setEnabled(True)
        # Soft check: warn (but don't block) if it doesn't look like a CoganLab root.
        looks_right = any((self._path / name).exists() for name in _EXPECTED)
        self._hint.setVisible(not looks_right)
        if not looks_right:
            self._hint.setText(
                "⚠ This folder doesn't contain D_Data / ECoG_Task_Data — make sure it's your "
                "CoganLab data root. You can still continue."
            )

    def chosen_path(self) -> Path | None:
        return self._path
