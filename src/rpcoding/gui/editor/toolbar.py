"""Editor toolbar: transport, label ops, selection readout, playback volume, theme toggle.

Amplitude lives in the waveform header now (＋/－); this bar keeps the playback volume slider (0–10×)
with an editable multiplier box beside it (up to 100× for very quiet audio) plus a non-modal
build-progress strip.
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

# The slider spans 0–10x (fine control); the editable box can go higher for very quiet audio.
_SLIDER_MAX_VOL = 10.0
_MAX_VOL = 100.0


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
    set_noise_profile_requested = Signal()  # capture the current selection as the noise profile
    denoise_requested = Signal(float)  # apply noise reduction at this strength (0..1)

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

        # Denoise (Audacity-style): set a noise profile from a noise-only selection, then reduce.
        lay.addWidget(self._sep())
        self._noise_btn = QPushButton("🔇 Noise profile")
        self._noise_btn.setToolTip("Set the noise profile from the selection (a noise-only span)")
        self._noise_btn.clicked.connect(self.set_noise_profile_requested.emit)
        lay.addWidget(self._noise_btn)
        self._noise_status = QLabel("no profile")
        self._noise_status.setObjectName("Meta")
        lay.addWidget(self._noise_status)
        self._strength = QSlider(Qt.Orientation.Horizontal)
        self._strength.setRange(0, 100)
        self._strength.setValue(80)
        self._strength.setFixedWidth(72)
        self._strength.setToolTip("Noise-reduction strength")
        self._strength.valueChanged.connect(lambda v: self._strength_val.setText(f"{v}%"))
        lay.addWidget(self._strength)
        self._strength_val = QLabel("80%")
        self._strength_val.setObjectName("Meta")
        self._strength_val.setFixedWidth(32)
        lay.addWidget(self._strength_val)
        self._denoise_btn = QPushButton("Denoise")
        self._denoise_btn.setToolTip("Reduce noise across the whole audio (profile + strength)")
        self._denoise_btn.setEnabled(False)
        self._denoise_btn.clicked.connect(
            lambda: self.denoise_requested.emit(self._strength.value() / 100.0)
        )
        lay.addWidget(self._denoise_btn)

        lay.addStretch(1)

        # Editable selection / label readout: click a field to type a precise start / end (seconds).
        self._sel_prefix = QLabel("sel")
        self._sel_prefix.setFixedWidth(34)
        lay.addWidget(self._sel_prefix)
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
        self._vol.setRange(0, int(_SLIDER_MAX_VOL * 100))  # 0x .. 10x (value / 100)
        self._vol.setValue(100)
        self._vol.setFixedWidth(96)
        self._vol.setToolTip("Playback volume (slider 0–10×; type a higher × in the box)")
        self._vol.valueChanged.connect(self._on_vol_changed)
        lay.addWidget(self._vol)
        # Editable multiplier: the slider caps at 10×, but very quiet recordings need more, so this
        # box accepts up to _MAX_VOL× (playback clips at ±1, so it just gets loud).
        self._vol_field = QLineEdit("1.0")
        self._vol_field.setObjectName("Mono")
        self._vol_field.setFixedWidth(46)
        self._vol_field.setValidator(QDoubleValidator(0.0, _MAX_VOL, 2, self._vol_field))
        self._vol_field.setToolTip(f"Type a playback multiplier (up to {_MAX_VOL:g}×)")
        self._vol_field.editingFinished.connect(self._on_vol_field_edited)
        lay.addWidget(self._vol_field)
        lay.addWidget(QLabel("×"))

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
        for s in (self._vol, self._strength):
            s.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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
        self._bar.setRange(0, 100)  # determinate (reset after a busy phase)
        self._bar.setValue(pct)
        if msg:
            self._status.setText(msg)

    def set_busy(self, msg: str = "") -> None:
        """Indeterminate (animated) progress bar for an operation with no measurable progress."""
        self._bar.setVisible(True)
        self._bar.setRange(0, 0)
        if msg:
            self._status.setText(msg)

    def set_noise_profile(self, span) -> None:
        """Show the captured noise-profile span and enable Denoise (or clear it when ``None``)."""
        if span is None:
            self._noise_status.setText("no profile")
            self._denoise_btn.setEnabled(False)
        else:
            a, b = span
            self._noise_status.setText(f"{a:.2f}–{b:.2f}s")
            self._denoise_btn.setEnabled(True)

    def set_denoise_busy(self, busy: bool) -> None:
        self._noise_btn.setEnabled(not busy)
        self._denoise_btn.setEnabled(not busy and self._noise_status.text() != "no profile")

    def build_done(self) -> None:
        self._bar.setRange(0, 100)
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
        gain = v / 100.0
        self.volume_changed.emit(gain)
        if not self._vol_field.hasFocus():  # don't clobber a value being typed
            self._vol_field.setText(f"{gain:.1f}")

    def _on_vol_field_edited(self) -> None:
        try:
            gain = float(self._vol_field.text())
        except ValueError:
            gain = self._vol.value() / 100.0  # revert to the slider on unparseable input
        gain = max(0.0, min(_MAX_VOL, gain))
        self.volume_changed.emit(gain)
        # Reflect on the slider (which only spans 0–10×) without re-emitting the clamped value.
        self._vol.blockSignals(True)
        self._vol.setValue(int(round(min(gain, _SLIDER_MAX_VOL) * 100)))
        self._vol.blockSignals(False)
        self._vol_field.setText(f"{gain:.1f}")

    def set_selection_text(self, span, is_label: bool = False) -> None:
        # ``is_label`` retitles the readout to "label" so the start/end/length refer to the selected
        # label (editing them retimes it), vs a free "sel" span. Don't clobber a field being edited.
        self._sel_prefix.setText("label" if (is_label and span is not None) else "sel")
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
