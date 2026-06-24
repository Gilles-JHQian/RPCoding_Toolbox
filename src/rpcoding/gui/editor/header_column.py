"""The 170px lane-header column (left of the plot column).

Per-track name + sub-label, the waveform amplitude control, and a focus highlight. Its fixed-height
rows are kept in lock-step with the pyqtgraph plot rows (identical heights, zero spacing, a bottom
stretch that soaks up the slack) so the two columns line up to the pixel — see the design prototype
``02 Annotation Editor.dc.html``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from rpcoding.gui.theme import MONO_FONT, Theme

HEADER_W = 170


class LaneHeaderColumn(QFrame):
    """Left header column; mirrors the plot rows and owns the amplitude buttons."""

    amp_up = Signal()
    amp_down = Signal()

    def __init__(self, theme: Theme, ruler_h: int, wave_h: int, spec_h: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LaneHeaderColumn")
        self.setFixedWidth(HEADER_W)
        self._theme = theme
        self._lane_rows: list[QFrame] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._time_row(ruler_h))
        root.addWidget(self._wave_row(wave_h))
        root.addWidget(self._spec_row(spec_h))
        self._lane_host = QWidget()
        self._lane_lay = QVBoxLayout(self._lane_host)
        self._lane_lay.setContentsMargins(0, 0, 0, 0)
        self._lane_lay.setSpacing(0)
        root.addWidget(self._lane_host)
        root.addStretch(1)  # the "＋ Add track" slack — mirrors the GLW's bottom stretch row
        self.apply_theme(theme)

    # ---- static row builders ----
    def _row_frame(self, height: int, obj: str = "HdrRow") -> QFrame:
        f = QFrame()
        f.setObjectName(obj)
        f.setFixedHeight(height)
        return f

    def _time_row(self, h: int) -> QFrame:
        f = self._row_frame(h)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 0, 12, 0)
        lab = QLabel("TIME · s")
        lab.setObjectName("HdrTime")
        lay.addWidget(lab)
        lay.addStretch(1)
        return f

    def _wave_row(self, h: int) -> QFrame:
        f = self._row_frame(h)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        name = QLabel("allblocks")
        name.setObjectName("HdrName")
        sub = QLabel("waveform · min/max")
        sub.setObjectName("HdrSub")
        lay.addWidget(name)
        lay.addWidget(sub)

        amp = QHBoxLayout()
        amp.setContentsMargins(0, 0, 0, 0)
        amp.setSpacing(6)
        amp_lab = QLabel("amp")
        amp_lab.setObjectName("HdrSub")
        minus = QPushButton("－")
        plus = QPushButton("＋")
        for b, sig in ((minus, self.amp_down), (plus, self.amp_up)):
            b.setObjectName("HdrAmpBtn")
            b.setFixedSize(22, 20)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(sig.emit)
        amp.addWidget(amp_lab)
        amp.addWidget(minus)
        amp.addWidget(plus)
        amp.addStretch(1)
        lay.addLayout(amp)
        lay.addStretch(1)
        return f

    def _spec_row(self, h: int) -> QFrame:
        f = self._row_frame(h)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        for text, obj in (
            ("allblocks", "HdrName"),
            ("spectrogram · dB", "HdrSub"),
            ("log-freq · 80–8k Hz", "HdrSub"),
        ):
            lab = QLabel(text)
            lab.setObjectName(obj)
            lay.addWidget(lab)
        lay.addStretch(1)
        return f

    # ---- dynamic lane rows ----
    def clear_lanes(self) -> None:
        while self._lane_lay.count():
            item = self._lane_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._lane_rows = []

    def add_lane(self, display: str, height: int, editable: bool) -> QFrame:
        f = QFrame()
        f.setObjectName("HdrRowResp" if editable else "HdrRow")
        f.setProperty("focused", False)
        f.setFixedHeight(height)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 0, 12, 0)
        name = QLabel(display + (" ✎" if editable else ""))
        name.setObjectName("HdrLaneResp" if editable else "HdrLane")
        lay.addWidget(name)
        lay.addStretch(1)
        self._lane_lay.addWidget(f)
        self._lane_rows.append(f)
        return f

    def set_focus(self, index: int) -> None:
        """Highlight the focused lane header (accent rail + soft fill); ``-1`` clears it."""
        for i, f in enumerate(self._lane_rows):
            focused = i == index
            if bool(f.property("focused")) != focused:
                f.setProperty("focused", focused)
                f.style().unpolish(f)
                f.style().polish(f)

    # ---- theme ----
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        p = theme.palette
        self.setStyleSheet(f"""
            QFrame#LaneHeaderColumn {{ background: {p['panel']}; border: none;
                                       border-right: 1px solid {p['border']}; }}
            QFrame#HdrRow, QFrame#HdrRowResp {{ background: transparent; border: none;
                border-bottom: 1px solid {p['border']}; border-left: 3px solid transparent; }}
            QFrame#HdrRowResp {{ background: {p['response-bg']}; }}
            QFrame#HdrRow[focused="true"], QFrame#HdrRowResp[focused="true"] {{
                background: {p['accent-soft']}; border-left-color: {p['accent']}; }}
            QLabel {{ background: transparent; border: none; }}
            QLabel#HdrTime {{ color: {p['text-ter']}; font-family: {MONO_FONT};
                              font-size: 10px; letter-spacing: 1px; }}
            QLabel#HdrName {{ color: {p['text-pri']}; font-size: 12px; font-weight: 600; }}
            QLabel#HdrSub {{ color: {p['text-ter']}; font-family: {MONO_FONT}; font-size: 10px; }}
            QLabel#HdrLane {{ color: {p['text-sec']}; font-family: {MONO_FONT};
                              font-size: 11px; font-weight: 500; }}
            QLabel#HdrLaneResp {{ color: {p['text-pri']}; font-family: {MONO_FONT};
                                  font-size: 11px; font-weight: 600; }}
            QPushButton#HdrAmpBtn {{ background: {p['btn-bg']}; border: 1px solid {p['btn-border']};
                                     border-radius: 4px; color: {p['text-sec']}; padding: 0; }}
            QPushButton#HdrAmpBtn:hover {{ border-color: {p['accent']}; color: {p['text-pri']}; }}
            """)
