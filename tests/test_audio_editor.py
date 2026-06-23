"""Audio editor tests (offscreen). Skipped where PySide6 / pyqtgraph aren't installed."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.editor.track_container import _LANE_H, _RULER_H
from rpcoding.gui.theme import DARK_THEME, LIGHT_THEME


def test_editor_constructs(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    assert ed.waveform is not None and ed.spectrogram is not None
    assert ed._wave_plot.maximumHeight() == _LANE_H
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
    assert abs(y0 + 0.5) < 1e-6 and abs(y1 - 0.5) < 1e-6  # +/- 1/gain


def test_add_label_lane(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    lane = ed.add_label_lane("cue_events")
    assert lane.name == "cue_events"
    assert lane.plot.getViewBox().linkedView(0) is ed._wave_plot.getViewBox()


def test_set_theme_does_not_raise(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_theme(LIGHT_THEME)


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
