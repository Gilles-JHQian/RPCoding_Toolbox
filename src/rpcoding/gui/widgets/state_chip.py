"""A capsule pill — a 7px colored dot + a state label on a soft-tinted background (design tokens).

When given an error ``detail`` it shows a tooltip and becomes clickable (emits ``clicked``) so the
dashboard can pop the full message.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from rpcoding.core.steps import EffectiveState
from rpcoding.gui.theme import RUNNING_LABEL, STATE_LABELS, Theme, soft_rgba


class StateChip(QFrame):
    clicked = Signal()

    def __init__(
        self, theme: Theme, state: EffectiveState = EffectiveState.NOT_STARTED, parent=None
    ):
        super().__init__(parent)
        self._theme = theme
        self._state = state
        self._detail: str | None = None
        self._running = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 3, 9, 3)
        lay.setSpacing(6)
        self._dot = QLabel()
        self._dot.setFixedSize(7, 7)
        self._dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text = QLabel("")
        self._text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._dot)
        lay.addWidget(self._text)
        self.set_state(state)

    def set_state(self, state: EffectiveState, detail: str | None = None) -> None:
        self._running = False
        self._state = state
        self._detail = detail
        self._apply(self._theme.state_color(state), STATE_LABELS.get(state, state.value), detail)

    def set_running(self) -> None:
        self._running = True
        self._detail = None
        self._apply(self._theme.running_color(), RUNNING_LABEL, None)

    def _apply(self, color: str, label: str, detail: str | None) -> None:
        soft = soft_rgba(color, self._theme.soft_alpha)
        self.setStyleSheet(f"QFrame {{ background: {soft}; border: none; border-radius: 11px; }}")
        self._dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
        self._text.setStyleSheet(
            f"color: {color}; background: transparent; font-size: 11px; font-weight: 600;"
        )
        self._text.setText(label)
        self.setToolTip(detail or "")
        self.setCursor(Qt.CursorShape.PointingHandCursor if detail else Qt.CursorShape.ArrowCursor)

    def text(self) -> str:
        return self._text.text()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._detail:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._running:
            self.set_running()
        else:
            self.set_state(self._state, self._detail)
