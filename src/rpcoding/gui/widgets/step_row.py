"""One pipeline step row: index, name + meta, state chip, and an action button."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind
from rpcoding.gui.theme import Theme
from rpcoding.gui.widgets.state_chip import StateChip

_RUNNABLE = {EffectiveState.NOT_STARTED, EffectiveState.DONE, EffectiveState.STALE}
_OPENABLE = {EffectiveState.NEEDS_MANUAL, EffectiveState.DONE, EffectiveState.STALE}


class StepRow(QWidget):
    action = Signal(object)  # emits the Step

    def __init__(self, theme: Theme, step: Step, index: int, parent=None):
        super().__init__(parent)
        self._step = step
        self._spec = STEP_SPECS[step]

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        idx = QLabel(str(index))
        idx.setObjectName("Meta")
        idx.setFixedWidth(20)
        lay.addWidget(idx)

        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(self._spec.title)
        name.setStyleSheet("font-weight: 500;")
        self._meta = QLabel("")
        self._meta.setObjectName("Meta")
        col.addWidget(name)
        col.addWidget(self._meta)
        lay.addLayout(col, 1)

        self._chip = StateChip(theme)
        lay.addWidget(self._chip)
        self._btn = QPushButton("Run")
        self._btn.clicked.connect(lambda: self.action.emit(self._step))
        lay.addWidget(self._btn)

    @property
    def step(self) -> Step:
        return self._step

    def set_state(self, state: EffectiveState, meta: str = "") -> None:
        self._chip.set_state(state)
        self._meta.setText(meta)
        if self._spec.kind == StepKind.MANUAL:
            self._btn.setText("Open editor")
            self._btn.setEnabled(state in _OPENABLE)
        else:
            self._btn.setText(
                "↻ Re-run" if state in (EffectiveState.DONE, EffectiveState.STALE) else "Run"
            )
            self._btn.setEnabled(state in _RUNNABLE)

    def set_theme(self, theme: Theme) -> None:
        self._chip.set_theme(theme)
