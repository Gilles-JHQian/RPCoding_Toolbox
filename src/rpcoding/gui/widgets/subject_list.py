"""Checkable subject list rendered with custom rows (dot · id · done/total)."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from rpcoding.core.steps import EffectiveState
from rpcoding.gui.theme import DARK_THEME, Theme
from rpcoding.gui.widgets.subject_row import SubjectRow


class SubjectList(QListWidget):
    subject_selected = Signal(str)

    def __init__(self, theme: Theme = DARK_THEME, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._rows: dict[str, SubjectRow] = {}
        self._items: dict[str, QListWidgetItem] = {}
        self.currentItemChanged.connect(self._on_change)

    def set_subjects(self, subjects: Iterable[str]) -> None:
        self.clear()
        self._rows = {}
        self._items = {}
        for s in subjects:
            item = QListWidgetItem(self)
            row = SubjectRow(s, self._theme)
            item.setSizeHint(row.sizeHint())
            self.addItem(item)
            self.setItemWidget(item, row)
            row.clicked.connect(lambda it=item: self.setCurrentItem(it))
            self._rows[s] = row
            self._items[s] = item

    def set_summary(
        self, subject: str, done: int | None, total: int | None, state: EffectiveState
    ) -> None:
        row = self._rows.get(subject)
        if row is not None:
            row.set_summary(done, total, state)

    def checked_subjects(self) -> list[str]:
        return [sid for sid, row in self._rows.items() if row.check.isChecked()]

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        for row in self._rows.values():
            row.set_theme(theme)

    def _on_change(self, current: QListWidgetItem | None, _previous) -> None:
        sel_id: str | None = None
        for sid, item in self._items.items():
            selected = item is current
            self._rows[sid].set_selected(selected)
            if selected:
                sel_id = sid
        if sel_id is not None:
            self.subject_selected.emit(sel_id)
