"""Settings dialog: edit the data root, word/nonword lists, and the per-task MFA config map.

Builds a new :class:`AppConfig` from the form on accept (``result_config``); the caller persists it
and refreshes any open sessions.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rpcoding.core.config import AppConfig
from rpcoding.core.tasks import Task


class _PathField(QWidget):
    """A line edit + Browse button for a file or directory path."""

    def __init__(self, value: str = "", *, directory: bool, caption: str, parent=None):
        super().__init__(parent)
        self._directory = directory
        self._caption = caption
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(value)
        lay.addWidget(self._edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        lay.addWidget(browse)

    def _browse(self) -> None:
        if self._directory:
            chosen = QFileDialog.getExistingDirectory(self, self._caption, self._edit.text())
        else:
            chosen, _ = QFileDialog.getOpenFileName(
                self, self._caption, self._edit.text(), "MATLAB files (*.mat);;All files (*)"
            )
        if chosen:
            self._edit.setText(chosen)

    def text(self) -> str:
        return self._edit.text().strip()


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(560, 320)

        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self._droot = _PathField(
            str(config.droot), directory=True, caption="CoganLab data root ($BOX/CoganLab)"
        )
        form.addRow("Data root", self._droot)

        self._word = _PathField(
            str(config.word_list) if config.word_list else "",
            directory=False,
            caption="Word list (.mat)",
        )
        form.addRow("Word list", self._word)
        self._nonword = _PathField(
            str(config.nonword_list) if config.nonword_list else "",
            directory=False,
            caption="Nonword list (.mat)",
        )
        form.addRow("Nonword list", self._nonword)

        outer.addWidget(QLabel("MFA task config (blank = unmapped)"))
        mfa_form = QFormLayout()
        outer.addLayout(mfa_form)
        self._mfa: dict[str, QLineEdit] = {}
        for task in Task:
            edit = QLineEdit(config.mfa_task(task) or "")
            self._mfa[task.value] = edit
            mfa_form.addRow(task.value, edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def result_config(self) -> AppConfig:
        """Build an :class:`AppConfig` from the current field values."""
        task_map = {name: (edit.text().strip() or None) for name, edit in self._mfa.items()}
        return AppConfig(
            droot=Path(self._droot.text()),
            mfa_task_map=task_map,
            word_list=Path(self._word.text()) if self._word.text() else None,
            nonword_list=Path(self._nonword.text()) if self._nonword.text() else None,
        )
