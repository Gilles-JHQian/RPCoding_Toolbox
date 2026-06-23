"""A subject-list row widget: checkbox · state dot · mono id · done/total."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget

from rpcoding.core.steps import EffectiveState
from rpcoding.gui.theme import Theme


class SubjectRow(QWidget):
    clicked = Signal()  # row body clicked (the checkbox consumes its own clicks)

    def __init__(self, subject: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.subject = subject
        self._theme = theme
        self._state = EffectiveState.NOT_STARTED
        self._done: int | None = None
        self._total: int | None = None
        self._selected = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 7, 14, 7)
        lay.setSpacing(10)
        self.check = QCheckBox()
        self.check.setChecked(True)
        lay.addWidget(self.check)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(11)
        lay.addWidget(self._dot)
        self._id = QLabel(subject)
        self._id.setObjectName("Mono")
        lay.addWidget(self._id)
        lay.addStretch(1)
        self._prog = QLabel("–/–")
        self._prog.setObjectName("Meta")
        lay.addWidget(self._prog)
        self._paint()

    def set_summary(self, done: int | None, total: int | None, state: EffectiveState) -> None:
        self._done, self._total, self._state = done, total, state
        self._paint()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._paint()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._paint()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.clicked.emit()
        super().mousePressEvent(event)

    def _paint(self) -> None:
        self._dot.setStyleSheet(f"color: {self._theme.state_color(self._state)}; font-size: 11px;")
        self._prog.setText(f"{self._done}/{self._total}" if self._total is not None else "–/–")
        self._id.setStyleSheet(f"color: {self._theme.color('text-pri')};")
        if self._selected:
            self.setStyleSheet(
                "SubjectRow { background: "
                + self._theme.color("accent-soft")
                + "; border-left: 3px solid "
                + self._theme.color("accent")
                + "; }"
            )
        else:
            self.setStyleSheet(
                "SubjectRow { background: transparent; border-left: 3px solid transparent; }"
            )
