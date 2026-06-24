"""Editor toolbar: transport, label ops, selection readout, playback volume, theme toggle.

Amplitude lives in the waveform header now (＋/－); this bar keeps the playback volume slider plus a
non-modal build-progress strip.
"""

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
    save_requested = Signal()
    back_requested = Signal()
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    fit_requested = Signal()
    play_requested = Signal()
    add_label_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    theme_toggle_requested = Signal()
    volume_changed = Signal(float)  # playback output gain
    selection_edited = Signal(float, float)  # start, end (seconds) typed into the readout

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)

        self._back = QPushButton("← Back")
        self._back.clicked.connect(self.back_requested.emit)
        lay.addWidget(self._back)

        self._play = QPushButton("▶ Play")
        self._play.setToolTip("Play / stop (Space)")
        self._play.clicked.connect(self.play_requested.emit)
        lay.addWidget(self._play)

        lay.addWidget(self._sep())
        for glyph, tip, sig in (
            ("🔍＋", "Zoom in", self.zoom_in_requested),
            ("🔍－", "Zoom out", self.zoom_out_requested),
            ("Fit", "Fit whole file", self.fit_requested),
        ):
            btn = QPushButton(glyph)
            btn.setToolTip(tip)
            btn.clicked.connect(sig.emit)
            lay.addWidget(btn)

        lay.addWidget(self._sep())
        self._add = QPushButton("＋ Label")
        self._add.setObjectName("Accent")
        self._add.setToolTip("Create label from selection (Ctrl+B)")
        self._add.clicked.connect(self.add_label_requested.emit)
        lay.addWidget(self._add)
        for text, tip, sig in (
            ("Copy", "Copy label (Ctrl+C)", self.copy_requested),
            ("Paste", "Paste label (Ctrl+V)", self.paste_requested),
        ):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.clicked.connect(sig.emit)
            lay.addWidget(btn)

        lay.addStretch(1)

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

        lay.addWidget(self._sep())
        lay.addWidget(QLabel("Vol"))
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 1000)  # 0x .. 10x playback gain (quiet recordings need a lot)
        self._vol.setValue(100)
        self._vol.setFixedWidth(96)
        self._vol.setToolTip("Playback volume (up to 10x)")
        self._vol.valueChanged.connect(self._on_vol_changed)
        lay.addWidget(self._vol)
        self._vol_val = QLabel("1.0×")
        self._vol_val.setObjectName("Meta")
        self._vol_val.setFixedWidth(34)
        lay.addWidget(self._vol_val)

        self._save = QPushButton("💾 Save")
        self._save.setObjectName("Primary")
        self._save.setToolTip("Save labels (Ctrl+S)")
        self._save.clicked.connect(self.save_requested.emit)
        lay.addWidget(self._save)

        self._theme = QPushButton("◑ Light")
        self._theme.setToolTip("Toggle dark / light theme")
        self._theme.clicked.connect(self.theme_toggle_requested.emit)
        lay.addWidget(self._theme)

        self._status = QLabel("")
        self._status.setObjectName("Meta")
        lay.addWidget(self._status)
        self._bar = QProgressBar()
        self._bar.setFixedWidth(150)
        self._bar.setRange(0, 100)
        self._bar.setVisible(False)
        lay.addWidget(self._bar)

        # Mouse-only controls: don't take keyboard focus, so Tab stays with the editor (label nav).
        for w in self.findChildren(QPushButton):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _sep(self) -> QFrame:
        line = QFrame()
        line.setObjectName("ToolSep")
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        return line

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

    def set_playing(self, playing: bool) -> None:
        self._play.setText("⏸ Stop" if playing else "▶ Play")

    def set_theme_name(self, name: str) -> None:
        """``name`` is the *current* theme; the button offers to switch to the other one."""
        self._theme.setText("◑ Light" if name == "dark" else "◑ Dark")

    def _on_vol_changed(self, v: int) -> None:
        self.volume_changed.emit(v / 100.0)
        self._vol_val.setText(f"{v / 100:.1f}×")

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
