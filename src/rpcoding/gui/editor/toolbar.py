"""Editor toolbar: amplitude scale, plus a non-modal build-progress strip."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QSlider


class EditorToolbar(QFrame):
    amplitude_changed = Signal(float)  # gain multiplier

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)

        lay.addWidget(QLabel("Amplitude"))
        self._amp = QSlider(Qt.Orientation.Horizontal)
        self._amp.setRange(10, 1000)  # 0.1x .. 10x
        self._amp.setValue(100)
        self._amp.setFixedWidth(140)
        self._amp.valueChanged.connect(lambda v: self.amplitude_changed.emit(v / 100.0))
        lay.addWidget(self._amp)

        lay.addStretch(1)
        self._status = QLabel("")
        self._status.setObjectName("Meta")
        lay.addWidget(self._status)
        self._bar = QProgressBar()
        self._bar.setFixedWidth(160)
        self._bar.setRange(0, 100)
        self._bar.setVisible(False)
        lay.addWidget(self._bar)

    def set_progress(self, pct: int, msg: str = "") -> None:
        self._bar.setVisible(True)
        self._bar.setValue(pct)
        if msg:
            self._status.setText(msg)

    def build_done(self) -> None:
        self._bar.setVisible(False)
        self._status.setText("Ready")
