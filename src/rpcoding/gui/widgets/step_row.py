"""One pipeline step row: index · state dot · name (+ manual tag) + meta · state chip · action."""

from __future__ import annotations

import html as _html

from PySide6.QtCore import QElapsedTimer, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
        self._last: tuple = (EffectiveState.NOT_STARTED, "", None, False)
        self._manual = self._spec.kind == StepKind.MANUAL
        # Denoise isn't a manual step but is also done in the editor (it needs the waveform to
        # pick a noise profile), so it gets the "Open editor" button too — just no "manual" tag.
        self._opens_editor = self._manual or step == Step.DENOISE

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
        # Second line, shown only while running: a thin determinate/indeterminate bar + live phase.
        self._prog_row = QWidget()
        prog_lay = QHBoxLayout(self._prog_row)
        prog_lay.setContentsMargins(0, 1, 0, 0)
        prog_lay.setSpacing(9)
        self._progress = QProgressBar()
        self._progress.setObjectName("StepProgress")
        self._progress.setTextVisible(False)
        self._progress.setFixedWidth(150)
        self._progress.setFixedHeight(6)
        prog_lay.addWidget(self._progress)
        self._status = QLabel("")
        self._status.setObjectName("Meta")
        prog_lay.addWidget(self._status, 1)
        self._prog_row.setVisible(False)
        col.addWidget(self._prog_row)
        lay.addLayout(col, 1)

        self._chip = StateChip(theme)
        self._chip.setFixedWidth(112)  # equal-width pills so the state column lines up
        self._chip.clicked.connect(lambda: self.error_details.emit(self._step))
        lay.addWidget(self._chip)

        self._btn = QPushButton("Run")
        self._btn.setFixedWidth(112)  # equal-width action column next to the chips
        self._btn.clicked.connect(lambda: self.action.emit(self._step))
        lay.addWidget(self._btn)

        # A 1 Hz elapsed-time clock so a long, quiet phase (e.g. MFA reading hundreds of stimulus
        # files from Box) visibly ticks instead of looking frozen.
        self._phase_msg = ""
        self._run_clock = QElapsedTimer()
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._render_status)

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

    def _render_status(self) -> None:
        """Show the latest phase message plus a live elapsed clock while the step runs."""
        if not self._run_clock.isValid():
            self._status.setText(self._phase_msg)
            return
        secs = self._run_clock.elapsed() // 1000
        clock = f"{secs // 60}:{secs % 60:02d}" if secs >= 60 else f"{secs}s"
        self._status.setText(f"{self._phase_msg} · {clock}" if self._phase_msg else clock)

    def set_running(self) -> None:
        self._dot.set_running()
        self._chip.set_running()
        self._btn.setText("Running…")
        self._btn.setEnabled(False)
        self._color_button(self._theme.running_color())
        # Swap the meta line for the live progress bar (indeterminate until the first real tick).
        self._meta.setVisible(False)
        self._prog_row.setVisible(True)
        self._progress.setRange(0, 0)
        self._phase_msg = "Starting…"
        self._run_clock.restart()
        self._clock_timer.start()
        self._render_status()

    def set_progress(self, fraction: float | None, message: str) -> None:
        """Update the inline bar while the step runs. ``fraction`` None = indeterminate (busy)."""
        if not self._prog_row.isVisible():  # a late tick after the row already reset
            self.set_running()
        if fraction is None:
            self._progress.setRange(0, 0)  # busy / indeterminate
        else:
            self._progress.setRange(0, 100)
            pct = 0 if fraction < 0 else 100 if fraction > 1 else int(round(fraction * 100))
            self._progress.setValue(pct)
        if message:
            self._phase_msg = message[:60]
        self._render_status()

    def set_state(
        self,
        state: EffectiveState,
        meta: str = "",
        error: str | None = None,
        log_available: bool = False,
    ) -> None:
        self._state = state
        self._last = (state, meta, error, log_available)
        self._clock_timer.stop()  # the step is no longer running; freeze the elapsed clock
        self._dot.set_state(state)
        # The chip is clickable when there's an error detail OR a run log to show (e.g. MFA).
        self._chip.set_state(
            state,
            detail=error if state == EffectiveState.ERROR else None,
            clickable=log_available,
        )
        # Back to the static meta line; hide the (now finished) progress bar.
        self._prog_row.setVisible(False)
        self._meta.setVisible(True)
        self._meta.setText(meta)
        self._render_name(blocked=state == EffectiveState.BLOCKED)
        self._apply_button(state)

    def _apply_button(self, state: EffectiveState) -> None:
        if self._opens_editor:
            self._btn.setText("Open editor")
            # Manual steps open when needs-manual/done/stale; Denoise opens whenever it's unblocked.
            openable = _OPENABLE | ({EffectiveState.NOT_STARTED} if not self._manual else set())
            self._btn.setEnabled(state in openable)
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
