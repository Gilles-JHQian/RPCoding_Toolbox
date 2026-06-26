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
    selection_changed = Signal()  # a checkbox toggled (drives the "K selected" count)

    def __init__(self, theme: Theme = DARK_THEME, parent=None):
        super().__init__(parent)
        self.setObjectName("SubjectList")
        self._theme = theme
        self._rows: dict[str, SubjectRow] = {}
        self._items: dict[str, QListWidgetItem] = {}
        self.currentItemChanged.connect(self._on_change)

    def set_subjects(self, subjects: Iterable[str]) -> None:
        self.clear()
        self._rows = {}
        self._items = {}
        for s in subjects:
            self._add_row(s)

    def _add_row(self, s: str) -> None:
        item = QListWidgetItem(self)
        row = SubjectRow(s, self._theme)
        item.setSizeHint(row.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, row)
        row.clicked.connect(lambda it=item: self.setCurrentItem(it))
        row.check.toggled.connect(lambda _c: self.selection_changed.emit())
        self._rows[s] = row
        self._items[s] = item

    def add_subject(self, subject: str) -> None:
        if subject and subject not in self._rows:
            self._add_row(subject)
            self.selection_changed.emit()

    def remove_subject(self, subject: str) -> None:
        item = self._items.pop(subject, None)
        if item is not None:
            self.takeItem(self.row(item))
            self._rows.pop(subject, None)
            self.selection_changed.emit()

    def set_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for sid, item in self._items.items():
            item.setHidden(bool(needle) and needle not in sid.lower())

    def set_summary(
        self,
        subject: str,
        done: int | None,
        total: int | None,
        state: EffectiveState,
        step_label: str = "",
    ) -> None:
        row = self._rows.get(subject)
        if row is not None:
            row.set_summary(done, total, state, step_label)

    def checked_subjects(self) -> list[str]:
        return [sid for sid, row in self._rows.items() if row.check.isChecked()]

    def selected_count(self) -> int:
        return sum(1 for row in self._rows.values() if row.check.isChecked())

    def current_subject(self) -> str | None:
        cur = self.currentItem()
        return next((sid for sid, item in self._items.items() if item is cur), None)

    def set_checked(self, subjects: Iterable[str]) -> None:
        wanted = set(subjects)
        for sid, row in self._rows.items():
            row.check.setChecked(sid in wanted)

    def set_all_checked(self, checked: bool) -> None:
        """Check / uncheck every row, emitting ``selection_changed`` once (not per row)."""
        for row in self._rows.values():
            row.check.blockSignals(True)
            row.check.setChecked(checked)
            row.check.blockSignals(False)
        self.selection_changed.emit()

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
