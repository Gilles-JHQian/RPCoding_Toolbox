"""Editor toolbar: amplitude scale, plus a non-modal build-progress strip."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSlider


class EditorToolbar(QFrame):
    amplitude_changed = Signal(float)  # gain multiplier
    save_requested = Signal()
    back_requested = Signal()
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    fit_requested = Signal()

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

        self._selection = QLabel("")
        self._selection.setObjectName("Meta")
        lay.addWidget(self._selection)

        lay.addStretch(1)
        self._hint = QLabel("drag waveform to select · Ctrl+B to label")
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
        if span is None:
            self._selection.setText("")
        else:
            a, b = span
            self._selection.setText(f"{a:.3f} – {b:.3f} s  ({b - a:.3f})")
