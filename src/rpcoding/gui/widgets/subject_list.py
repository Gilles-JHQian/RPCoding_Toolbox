"""Checkable list of subjects; emits the selected subject id."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class SubjectList(QListWidget):
    subject_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentItemChanged.connect(self._on_change)

    def set_subjects(self, subjects: Iterable[str]) -> None:
        self.clear()
        for s in subjects:
            item = QListWidgetItem(s)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.addItem(item)

    def checked_subjects(self) -> list[str]:
        return [
            self.item(i).text()
            for i in range(self.count())
            if self.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _on_change(self, current: QListWidgetItem | None, _previous) -> None:
        if current is not None:
            self.subject_selected.emit(current.text())
