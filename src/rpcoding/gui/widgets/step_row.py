"""One pipeline step row: index · state dot · name (+ manual tag) + meta · state chip · action."""

from __future__ import annotations

import html as _html

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step, StepKind
from rpcoding.gui.theme import MONO_FONT, Theme
from rpcoding.gui.widgets.state_chip import StateChip
from rpcoding.gui.widgets.state_dot import StateDot

_RUNNABLE = {
    EffectiveState.NOT_STARTED,
    EffectiveState.DONE,
    EffectiveState.STALE,
    EffectiveState.ERROR,
}
_OPENABLE = {EffectiveState.NEEDS_MANUAL, EffectiveState.DONE, EffectiveState.STALE}
# Filenames the prototype renders in monospace inside the otherwise-sans step titles.
_FILE_TOKENS = ("allblocks.wav", "trialInfo.mat", "first_stims.txt", "Trials.mat")
_RERUN = {EffectiveState.DONE, EffectiveState.STALE, EffectiveState.ERROR}


class StepRow(QWidget):
    action = Signal(object)  # emits the Step (run / open editor)
    error_details = Signal(object)  # emits the Step when its error chip is clicked

    def __init__(self, theme: Theme, step: Step, index: int, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._step = step
        self._spec = STEP_SPECS[step]
        self._state = EffectiveState.NOT_STARTED
        self._last: tuple = (EffectiveState.NOT_STARTED, "", None)
        self._manual = self._spec.kind == StepKind.MANUAL

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 13, 0, 13)
        lay.setSpacing(15)

        self._idx = QLabel(str(index))
        self._idx.setObjectName("StepIndex")
        self._idx.setFixedWidth(16)
        lay.addWidget(self._idx)

        self._dot = StateDot(theme)
        lay.addWidget(self._dot)

        col = QVBoxLayout()
        col.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)
        self._name = QLabel()
        name_row.addWidget(self._name)
        self._manual_tag = QLabel("manual")
        self._manual_tag.setVisible(self._manual)
        name_row.addWidget(self._manual_tag)
        name_row.addStretch(1)
        col.addLayout(name_row)
        self._meta = QLabel("")
        self._meta.setObjectName("Meta")
        col.addWidget(self._meta)
        lay.addLayout(col, 1)

        self._chip = StateChip(theme)
        self._chip.clicked.connect(lambda: self.error_details.emit(self._step))
        lay.addWidget(self._chip)

        self._btn = QPushButton("Run")
        self._btn.clicked.connect(lambda: self.action.emit(self._step))
        lay.addWidget(self._btn)

        self._render_name(blocked=False)

    @property
    def step(self) -> Step:
        return self._step

    def _title_html(self) -> str:
        title = _html.escape(self._spec.title)
        for tok in _FILE_TOKENS:
            esc = _html.escape(tok)
            title = title.replace(esc, f"<span style='font-family:{MONO_FONT};'>{esc}</span>")
        return title

    def _render_name(self, blocked: bool) -> None:
        color = self._theme.color("text-ter" if blocked else "text-pri")
        self._name.setStyleSheet(f"font-size: 14px; color: {color};")
        self._name.setText(self._title_html())
        if self._manual:
            purple = self._theme.state_color(EffectiveState.NEEDS_MANUAL)
            self._manual_tag.setStyleSheet(
                f"color: {purple}; font-size: 11px; background: transparent;"
            )

    def set_running(self) -> None:
        self._dot.set_running()
        self._chip.set_running()
        self._meta.setText("running…")
        self._btn.setText("Running…")
        self._btn.setEnabled(False)
        self._color_button(self._theme.running_color())

    def set_state(self, state: EffectiveState, meta: str = "", error: str | None = None) -> None:
        self._state = state
        self._last = (state, meta, error)
        self._dot.set_state(state)
        self._chip.set_state(state, detail=error if state == EffectiveState.ERROR else None)
        self._meta.setText(meta)
        self._render_name(blocked=state == EffectiveState.BLOCKED)
        self._apply_button(state)

    def _apply_button(self, state: EffectiveState) -> None:
        if self._spec.kind == StepKind.MANUAL:
            self._btn.setText("Open editor")
            self._btn.setEnabled(state in _OPENABLE)
            # Always the manual-purple outline (matches the prototype), even when locked.
            purple = self._theme.state_color(EffectiveState.NEEDS_MANUAL)
            self._color_button(purple, weight="600", pad="7px 14px")
            return
        if state == EffectiveState.BLOCKED:
            self._btn.setText("Run")
            self._btn.setEnabled(False)
            self._color_button(None)
            return
        self._btn.setEnabled(state in _RUNNABLE)
        self._btn.setText("↻ Re-run" if state in _RERUN else "Run")
        # Only stale gets an accent outline; error stays neutral (its dot + chip carry the red).
        stale = state == EffectiveState.STALE
        self._color_button(self._theme.state_color(EffectiveState.STALE) if stale else None)

    def _color_button(self, color: str | None, weight: str = "400", pad: str = "6px 12px") -> None:
        if color:
            self._btn.setStyleSheet(
                f"border: 1px solid {color}; color: {color}; border-radius: 7px;"
                f"padding: {pad}; font-weight: {weight};"
            )
        else:
            self._btn.setStyleSheet("")  # fall back to the global QSS button style

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._dot.set_theme(theme)
        self._chip.set_theme(theme)
        self.set_state(*self._last)
