"""Audio editor tests (offscreen). Skipped where PySide6 / pyqtgraph aren't installed."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QPointF, Qt

from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.editor.interactive_viewbox import InteractiveViewBox
from rpcoding.gui.editor.track_container import _RULER_H, _SPEC_H, _WAVE_H
from rpcoding.gui.theme import DARK_THEME, LIGHT_THEME


class _FakeWheel:
    def __init__(self, delta, mods):
        self._d, self._m, self.accepted = delta, mods, None

    def delta(self):
        return self._d

    def modifiers(self):
        return self._m

    def scenePos(self):
        return QPointF(0.0, 0.0)

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


class _FakeDrag:
    def __init__(self, button, down, now, is_start=True):
        self._b, self._down, self._now, self._start = button, down, now, is_start
        self.accepted = False

    def button(self):
        return self._b

    def buttonDownScenePos(self):
        return self._down

    def scenePos(self):
        return self._now

    def isStart(self):
        return self._start

    def accept(self):
        self.accepted = True


def test_editor_constructs(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    assert ed.waveform is not None and ed.spectrogram is not None
    assert ed._wave_plot.maximumHeight() == _WAVE_H
    assert ed._ruler.maximumHeight() == _RULER_H


def test_xlink_propagates(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_visible_range(1.0, 2.0)
    wx = ed._wave_plot.getViewBox().viewRange()[0]
    sx = ed._spec_plot.getViewBox().viewRange()[0]
    assert abs(wx[0] - sx[0]) < 1e-6 and abs(wx[1] - sx[1]) < 1e-6


def test_amplitude_scale_pure_y(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_amplitude_scale(2.0)
    y0, y1 = ed._wave_plot.getViewBox().viewRange()[1]
    # +/- peak*1.1/gain; default peak 1.0 -> +/-0.55
    assert abs(y0 + 0.55) < 1e-6 and abs(y1 - 0.55) < 1e-6


def test_add_label_lane(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    lane = ed.add_label_lane("cue_events")
    assert lane.name == "cue_events"
    assert lane.plot.getViewBox().linkedView(0) is ed._wave_plot.getViewBox()


def test_edit_selected_label_retimes_it(qtbot):
    from rpcoding.core.labels import Interval, Tier

    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(1.0, 2.0, "x")]), True)])
    lane = ed._label_lanes[0]
    ed._select_only(lane)
    lane.select(0)
    assert ed._toolbar._sel_prefix.text() == "label"  # readout retitled to the label
    ed._on_selection_edited(1.5, 3.0)  # typing into the start/end fields retimes the label
    iv = lane.active_interval()
    assert abs(iv.start - 1.5) < 1e-9 and abs(iv.end - 3.0) < 1e-9
    assert ed.selection() == (1.5, 3.0)  # the mirrored selection follows the label


def test_header_column_tracks_tiers(qtbot):
    from rpcoding.core.labels import Tier

    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers(
        [("cue_events", Tier("cue_events", []), False), ("response", Tier("response", []), True)]
    )
    assert len(ed._header._lane_rows) == 2  # one header row per lane, kept in step with the plots
    ed.set_tiers([("response", Tier("response", []), True)])
    assert len(ed._header._lane_rows) == 1  # rebuilt, never stacked


def test_header_focus_follows_selection(qtbot):
    from rpcoding.core.labels import Interval, Tier

    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers(
        [
            ("cue_events", Tier("cue_events", [Interval(1, 2, "a")]), False),
            ("response", Tier("response", [Interval(1, 2, "b")]), True),
        ]
    )
    ed._select_only(ed._label_lanes[0])
    assert [bool(r.property("focused")) for r in ed._header._lane_rows] == [True, False]


def test_histogram_capped_to_spec_row(qtbot):
    # The histogram must not inflate the spectrogram row, or the lanes drift off the header column.
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    assert ed._hist.maximumHeight() == _SPEC_H


def test_set_theme_does_not_raise(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_theme(LIGHT_THEME)


def test_theme_switch_updates_background(qtbot):
    from rpcoding.core.labels import Tier

    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    dark_bg = ed._glw.backgroundBrush().color().name().lower()
    ed.set_theme(LIGHT_THEME)
    light_bg = ed._glw.backgroundBrush().color().name().lower()
    assert dark_bg != light_bg and light_bg == "#f3f5f9"  # light lane-bg (plot surface)


def test_all_lanes_interactive(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.add_label_lane("cue_events")
    lanes = [ed._ruler, ed._wave_plot, ed._spec_plot, *ed._lane_plots]
    assert all(isinstance(p.getViewBox(), InteractiveViewBox) for p in lanes)


def test_interactive_viewbox_wheel(qtbot, monkeypatch):
    vb = InteractiveViewBox()
    monkeypatch.setattr(vb, "mapSceneToView", lambda _p: QPointF(5.0, 0.0))
    zooms: list = []
    pans: list = []
    vb.zoom_requested.connect(lambda c, f: zooms.append((c, f)))
    vb.pan_requested.connect(pans.append)

    vb.wheelEvent(_FakeWheel(120, Qt.KeyboardModifier.ControlModifier))
    assert zooms and zooms[0][0] == 5.0 and zooms[0][1] < 1.0  # Ctrl+wheel-up zooms in about cursor

    vb.wheelEvent(_FakeWheel(120, Qt.KeyboardModifier.ShiftModifier))
    assert pans and pans[0] < 0  # Shift+wheel pans

    plain = _FakeWheel(120, Qt.KeyboardModifier.NoModifier)
    vb.wheelEvent(plain)
    assert plain.accepted is False  # plain wheel is a no-op


def test_interactive_viewbox_drag_selects(qtbot, monkeypatch):
    vb = InteractiveViewBox()
    monkeypatch.setattr(vb, "mapSceneToView", lambda p: p)  # identity (scene x == time)
    spans: list = []
    vb.region_dragged.connect(lambda a, b, s: spans.append((a, b, s)))
    vb.mouseDragEvent(_FakeDrag(Qt.MouseButton.LeftButton, QPointF(3.0, 0.0), QPointF(7.0, 0.0)))
    assert spans == [(3.0, 7.0, True)]


def test_load_synth_wav(qtbot, tmp_path):
    pytest.importorskip("scipy")
    pytest.importorskip("soundfile")
    from rpcoding.core.audio.io import write_wav
    from rpcoding.core.audio.render.cache import AudioRenderCache

    fs = 16000
    t = np.arange(fs) / fs
    x = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav = tmp_path / "allblocks.wav"
    write_wav(wav, x, fs)
    cache = tmp_path / "cache"

    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    with qtbot.waitSignal(ed.load_finished, timeout=20000):
        ed.load(wav, cache)

    c = AudioRenderCache(cache)
    key = c.content_key(wav)
    assert c.pyramid_path(key).exists()
    assert list((cache / key / "spectro").glob("*/spec.npy"))
    assert abs(ed.duration() - 1.0) < 0.05


def test_denoise_profile_enables_button(qtbot, tmp_path):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.configure_denoise(tmp_path / "allblocks.wav", tmp_path / "allblocks_original.wav")
    assert not ed._toolbar._denoise_btn.isEnabled()  # no profile yet
    ed.set_selection((1.0, 2.0))
    ed._set_noise_profile()  # capture the selection as the noise profile
    assert ed._noise_profile == (1.0, 2.0)
    assert ed._toolbar._denoise_btn.isEnabled()


def test_denoise_apply_writes_result_and_backs_up_raw(qtbot, tmp_path, monkeypatch):
    pytest.importorskip("noisereduce")
    from rpcoding.core.audio.io import read_wav, write_wav

    fs = 8000
    rng = np.random.default_rng(0)
    t = np.arange(2 * fs) / fs
    tone = 0.3 * np.sin(2 * np.pi * 220 * t)
    tone[fs:] = 0.0  # second half is noise-only
    sig = (tone + 0.05 * rng.standard_normal(2 * fs)).astype(np.float32)
    allblocks = tmp_path / "allblocks.wav"
    original = tmp_path / "allblocks_original.wav"
    write_wav(allblocks, sig, fs)

    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.configure_denoise(allblocks, original)
    ed.set_selection((1.2, 1.8))  # a noise-only span
    ed._set_noise_profile()
    # Stub the post-denoise reload: the real reload spawns render workers we don't need here (and
    # whose dangling threads would crash teardown). load() is covered by test_load_synth_wav.
    reloaded: list = []
    monkeypatch.setattr(ed, "load", lambda *a, **k: reloaded.append(a))
    with qtbot.waitSignal(ed.denoised, timeout=20000):
        ed._apply_denoise(1.0)
    assert reloaded  # the result was reloaded after denoising

    assert original.exists()  # the raw signal is preserved
    out, _ = read_wav(allblocks)
    noise = slice(int(1.2 * fs), 2 * fs)
    assert np.std(out[noise]) < np.std(sig[noise]) * 0.85  # noise floor reduced on disk
