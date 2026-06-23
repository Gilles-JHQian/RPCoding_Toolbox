"""A small pill label coloured by a step's effective state."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from rpcoding.core.steps import EffectiveState
from rpcoding.gui.theme import STATE_LABELS, Theme


class StateChip(QLabel):
    def __init__(
        self, theme: Theme, state: EffectiveState = EffectiveState.NOT_STARTED, parent=None
    ):
        super().__init__(parent)
        self._theme = theme
        self._state = state
        self.set_state(state)

    def set_state(self, state: EffectiveState) -> None:
        self._state = state
        color = self._theme.state_color(state)
        self.setText(f"● {STATE_LABELS.get(state, state.value)}")
        self.setStyleSheet(
            f"color: {color}; padding: 2px 9px; border: 1px solid {color};"
            "border-radius: 11px; font-size: 11px;"
        )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.set_state(self._state)
