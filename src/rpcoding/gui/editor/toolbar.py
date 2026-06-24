"""Editor toolbar: amplitude scale, plus a non-modal build-progress strip."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
)


class EditorToolbar(QFrame):
    amplitude_changed = Signal(float)  # gain multiplier
    save_requested = Signal()
    back_requested = Signal()
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    fit_requested = Signal()
    selection_edited = Signal(float, float)  # start, end (seconds) typed into the readout

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        self._back = QPushButton("← Back")
        self._back.clicked.connect(self.back_requested.emit)
        lay.addWidget(self._back)

        for glyph, tip, sig in (
            ("🔍＋", "Zoom in", self.zoom_in_requested),
            ("🔍－", "Zoom out", self.zoom_out_requested),
            ("Fit", "Fit whole file", self.fit_requested),
        ):
            btn = QPushButton(glyph)
            btn.setToolTip(tip)
            btn.clicked.connect(sig.emit)
            lay.addWidget(btn)

        lay.addWidget(QLabel("Amp"))
        self._amp = QSlider(Qt.Orientation.Horizontal)
        self._amp.setRange(10, 1000)  # 0.1x .. 10x
        self._amp.setValue(100)
        self._amp.setFixedWidth(120)
        self._amp.valueChanged.connect(lambda v: self.amplitude_changed.emit(v / 100.0))
        lay.addWidget(self._amp)

        # Editable selection readout: click a field to type a precise start / end (seconds).
        lay.addWidget(QLabel("sel"))
        self._sel_start = self._make_time_field("start")
        lay.addWidget(self._sel_start)
        lay.addWidget(QLabel("–"))
        self._sel_end = self._make_time_field("end")
        lay.addWidget(self._sel_end)
        self._sel_dur = QLabel("")
        self._sel_dur.setObjectName("Meta")
        lay.addWidget(self._sel_dur)

        lay.addStretch(1)
        self._hint = QLabel("drag to select · Ctrl+B to label")
        self._hint.setObjectName("Meta")
        lay.addWidget(self._hint)

        self._save = QPushButton("💾 Save (Ctrl+S)")
        self._save.setObjectName("Primary")
        self._save.clicked.connect(self.save_requested.emit)
        lay.addWidget(self._save)

        self._status = QLabel("")
        self._status.setObjectName("Meta")
        lay.addWidget(self._status)
        self._bar = QProgressBar()
        self._bar.setFixedWidth(160)
        self._bar.setRange(0, 100)
        self._bar.setVisible(False)
        lay.addWidget(self._bar)

        # Mouse-only controls: don't take keyboard focus, so Tab stays with the editor (label nav).
        for w in self.findChildren(QPushButton):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._amp.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _make_time_field(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("Mono")
        field.setFixedWidth(76)
        field.setPlaceholderText(placeholder)
        field.setValidator(QDoubleValidator(0.0, 1e7, 6, field))
        field.editingFinished.connect(self._emit_selection_edit)
        return field

    def _emit_selection_edit(self) -> None:
        try:
            a = float(self._sel_start.text())
            b = float(self._sel_end.text())
        except ValueError:
            return
        if a != b:
            self.selection_edited.emit(min(a, b), max(a, b))

    def set_progress(self, pct: int, msg: str = "") -> None:
        self._bar.setVisible(True)
        self._bar.setValue(pct)
        if msg:
            self._status.setText(msg)

    def build_done(self) -> None:
        self._bar.setVisible(False)
        self._status.setText("Ready")

    def set_status(self, msg: str) -> None:
        self._status.setText(msg)

    def set_selection_text(self, span) -> None:
        # Don't clobber a field the user is currently typing into.
        if span is None:
            if not self._sel_start.hasFocus():
                self._sel_start.clear()
            if not self._sel_end.hasFocus():
                self._sel_end.clear()
            self._sel_dur.setText("")
        else:
            a, b = span
            if not self._sel_start.hasFocus():
                self._sel_start.setText(f"{a:.3f}")
            if not self._sel_end.hasFocus():
                self._sel_end.setText(f"{b:.3f}")
            self._sel_dur.setText(f"({b - a:.3f} s)")
