"""One pipeline step row: index · state dot · name + meta · state chip · action button."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind
from rpcoding.gui.theme import Theme
from rpcoding.gui.widgets.state_chip import StateChip
from rpcoding.gui.widgets.state_dot import StateDot

_RUNNABLE = {
    EffectiveState.NOT_STARTED,
    EffectiveState.DONE,
    EffectiveState.STALE,
    EffectiveState.ERROR,
}
_OPENABLE = {EffectiveState.NEEDS_MANUAL, EffectiveState.DONE, EffectiveState.STALE}


class StepRow(QWidget):
    action = Signal(object)  # emits the Step (run / open editor)
    error_details = Signal(object)  # emits the Step when its error chip is clicked

    def __init__(self, theme: Theme, step: Step, index: int, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._step = step
        self._spec = STEP_SPECS[step]
        self._state = EffectiveState.NOT_STARTED

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(14)

        self._idx = QLabel(str(index))
        self._idx.setObjectName("Meta")
        self._idx.setFixedWidth(16)
        lay.addWidget(self._idx)

        self._dot = StateDot(theme)
        lay.addWidget(self._dot)

        col = QVBoxLayout()
        col.setSpacing(3)
        self._name = QLabel(self._spec.title)
        self._name.setStyleSheet("font-size: 14px;")
        self._meta = QLabel("")
        self._meta.setObjectName("Meta")
        col.addWidget(self._name)
        col.addWidget(self._meta)
        lay.addLayout(col, 1)

        self._chip = StateChip(theme)
        self._chip.clicked.connect(lambda: self.error_details.emit(self._step))
        lay.addWidget(self._chip)

        self._btn = QPushButton("Run")
        self._btn.clicked.connect(lambda: self.action.emit(self._step))
        lay.addWidget(self._btn)

    @property
    def step(self) -> Step:
        return self._step

    def set_running(self) -> None:
        self._dot.set_running()
        self._chip.set_running()
        self._meta.setText("running…")
        self._btn.setText("Running…")
        self._btn.setEnabled(False)
        self._color_button(self._theme.running_color())

    def set_state(self, state: EffectiveState, meta: str = "", error: str | None = None) -> None:
        self._state = state
        self._dot.set_state(state)
        self._chip.set_state(state, detail=error if state == EffectiveState.ERROR else None)
        self._meta.setText(meta)
        self._name.setStyleSheet(
            "font-size: 14px; color: "
            + self._theme.color("text-ter" if state == EffectiveState.BLOCKED else "text-pri")
        )
        self._apply_button(state)

    def _apply_button(self, state: EffectiveState) -> None:
        if self._spec.kind == StepKind.MANUAL:
            self._btn.setText("Open editor")
            enabled = state in _OPENABLE
            self._btn.setEnabled(enabled)
            self._color_button(
                self._theme.state_color(EffectiveState.NEEDS_MANUAL) if enabled else None
            )
            return
        if state == EffectiveState.BLOCKED:
            self._btn.setText("Run")
            self._btn.setEnabled(False)
            self._color_button(None)
            return
        self._btn.setEnabled(state in _RUNNABLE)
        self._btn.setText(
            "↻ Re-run"
            if state in (EffectiveState.DONE, EffectiveState.STALE, EffectiveState.ERROR)
            else "Run"
        )
        accent = {
            EffectiveState.STALE: self._theme.state_color(EffectiveState.STALE),
            EffectiveState.ERROR: self._theme.state_color(EffectiveState.ERROR),
        }.get(state)
        self._color_button(accent)

    def _color_button(self, color: str | None) -> None:
        if color:
            self._btn.setStyleSheet(
                f"border: 1px solid {color}; color: {color}; border-radius: 7px; padding: 6px 12px;"
            )
        else:
            self._btn.setStyleSheet("")  # fall back to the global QSS button style

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._dot.set_theme(theme)
        self._chip.set_theme(theme)
