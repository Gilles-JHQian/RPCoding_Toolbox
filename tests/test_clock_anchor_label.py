"""Ctrl+B on the clock_anchors lane defaults the new label to the overlapping trial number."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from rpcoding.core.labels import Interval, Tier
from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.editor import track_container as tc
from rpcoding.gui.theme import DARK_THEME

_CUE = Tier("cue_events", [Interval(4.0, 5.0, "1_a.wav"), Interval(10.0, 11.0, "2_b.wav")])


@pytest.fixture(autouse=True, scope="module")
def _safe_dialogs():
    # These tests leave the editor dirty; pytest-qt's teardown close() would fire the save prompt.
    orig = tc.QMessageBox.question
    tc.QMessageBox.question = lambda *a, **k: tc.QMessageBox.StandardButton.Discard
    yield
    tc.QMessageBox.question = orig


def _editor(qtbot, editable_name: str):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("cue_events", _CUE, False), (editable_name, Tier(editable_name, []), True)])
    return ed


def _new_label(ed) -> str:
    return ed._editable_lane.get_tier().intervals[-1].label


def test_clock_anchor_defaults_to_overlapping_trial(qtbot):
    ed = _editor(qtbot, "clock_anchors")
    ed.set_selection((10.2, 10.8))  # over trial 2's cue box
    ed._create_label_from_selection()
    assert _new_label(ed) == "2"


def test_clock_anchor_uses_nearest_when_between_boxes(qtbot):
    ed = _editor(qtbot, "clock_anchors")
    ed.set_selection((9.0, 9.5))  # in the gap; nearest cue box is trial 2's
    ed._create_label_from_selection()
    assert _new_label(ed) == "2"


def test_non_clock_lane_gets_empty_label(qtbot):
    ed = _editor(qtbot, "response")
    ed.set_selection((10.2, 10.8))
    ed._create_label_from_selection()
    assert _new_label(ed) == ""  # only the clock_anchors lane pre-fills the trial number
