"""An 18px circular status dot: filled with a ✓ when done, ``!`` on error, ● while running."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from rpcoding.core.steps import EffectiveState
from rpcoding.gui.theme import Theme, soft_rgba


class StateDot(QLabel):
    def __init__(
        self, theme: Theme, state: EffectiveState = EffectiveState.NOT_STARTED, parent=None
    ):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._theme = theme
        self._state = state
        self._running = False
        self.set_state(state)

    def set_state(self, state: EffectiveState) -> None:
        self._running = False
        self._state = state
        glyph = {EffectiveState.DONE: "✓", EffectiveState.ERROR: "!"}.get(state, "")
        self._apply(self._theme.state_color(state), glyph, filled=state == EffectiveState.DONE)

    def set_running(self) -> None:
        self._running = True
        self._apply(self._theme.running_color(), "●", filled=False)

    def _apply(self, color: str, glyph: str, filled: bool) -> None:
        bg = color if filled else soft_rgba(color, self._theme.soft_alpha)
        self.setText(glyph)
        self.setStyleSheet(
            f"background: {bg}; border: 1.5px solid {color}; border-radius: 9px;"
            "color: #ffffff; font-size: 10px; font-weight: 600;"
        )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._running:
            self.set_running()
        else:
            self.set_state(self._state)
