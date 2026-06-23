"""Editor save / clear-on-reopen behavior (offscreen). Skipped where PySide6/pyqtgraph absent."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from rpcoding.core.labels import Interval, Tier, read_tier
from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.theme import DARK_THEME


def test_editor_save_writes_focused_tier(qtbot, tmp_path):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers(
        [
            ("cue_events", Tier("cue_events", [Interval(1, 2, "1_x.wav")]), False),
            ("response", Tier("response", []), True),
        ]
    )
    save_path = tmp_path / "bsliang_resp_words_errors.txt"
    ed.configure_save(save_path)

    saw: list = []
    ed.saved.connect(lambda: saw.append(True))

    ed.set_selection((3.0, 4.0))
    ed._create_label_from_selection()  # Ctrl+B on the focused (response) lane
    ed.save()

    assert saw == [True]
    tier = read_tier(save_path)
    assert len(tier.intervals) == 1
    assert tier.intervals[0].start == pytest.approx(3.0)


def test_editor_save_noop_without_target(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    saw: list = []
    ed.saved.connect(lambda: saw.append(True))
    ed.save()  # no configure_save() -> silently does nothing
    assert saw == []


def test_editor_clear_tiers_on_reopen(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers(
        [
            ("cue_events", Tier("cue_events", [Interval(1, 2, "1_x.wav")]), False),
            ("response", Tier("response", []), True),
        ]
    )
    assert len(ed._label_lanes) == 2

    # Reopening on a different step must not stack lanes.
    ed.set_tiers([("first_stims", Tier("first_stims", []), True)])
    assert len(ed._label_lanes) == 1
    assert ed._focus_lane is not None and ed._focus_lane.name == "first_stims"
    # one spectrogram mirror + one lane mirror
    assert len(ed._sel_regions) == 2


def test_editor_back_signal(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    saw: list = []
    ed.back_requested.connect(lambda: saw.append(True))
    ed._toolbar.back_requested.emit()
    assert saw == [True]
