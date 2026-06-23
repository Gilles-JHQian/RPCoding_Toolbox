"""Label-track editing tests (offscreen). Skipped where PySide6/pyqtgraph aren't installed."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PySide6.QtWidgets import QPushButton

from rpcoding.core.labels import Interval, Tier
from rpcoding.core.trial_index import TrialInfo
from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.editor.label_lane import LabelLane
from rpcoding.gui.editor.selection import SelectionModel
from rpcoding.gui.editor.trial_info_panel import TrialInfoPanel
from rpcoding.gui.theme import DARK_THEME


def _plot(qtbot) -> pg.PlotItem:
    w = pg.GraphicsLayoutWidget()
    qtbot.addWidget(w)
    p = w.addPlot()
    p._keepalive = w  # keep the host widget (and its ViewBox) from being GC'd
    return p


def test_selection_model_normalizes():
    sm = SelectionModel()
    seen: list = []
    sm.changed.connect(seen.append)
    sm.set_span((5.0, 2.0))
    assert sm.span() == (2.0, 5.0)
    assert seen == [(2.0, 5.0)]
    sm.clear()
    assert sm.span() is None


def test_label_lane_crud_and_nav(qtbot):
    lane = LabelLane(_plot(qtbot), "response", DARK_THEME, editable=True)
    lane.set_tier(Tier("response", [Interval(1, 2, "a"), Interval(3, 4, "b")]))
    assert len(lane.intervals()) == 2

    lane.create(5, 6, "c")  # appends + selects
    assert lane.active_interval().label == "c"
    lane.rename_active("c2")
    assert lane.active_interval().label == "c2"

    first = lane.select_step(1)  # wraps from c2 -> a (by start time)
    assert first.start == 1
    lane.delete_active()  # removes 'a'
    labels = [iv.label for iv in lane.get_tier().intervals]
    assert "a" not in labels and labels == ["b", "c2"]


def test_label_lane_virtualizes(qtbot):
    lane = LabelLane(_plot(qtbot), "cue", DARK_THEME, editable=False)
    lane.set_tier(Tier("cue", [Interval(i, i + 0.5, f"l{i}") for i in range(1000)]))
    lane.set_view(0, 1000, 1000)  # everything in view -> capped, not 1000 items
    assert lane._used <= 241  # _MAX_RENDER (+ possibly the active one)
    lane.set_view(10.0, 20.0, 800)  # a narrow window -> only its handful render
    assert lane._used <= 24
    # the data is untouched by culling
    assert len(lane.intervals()) == 1000


def test_label_lane_readonly_not_movable(qtbot):
    lane = LabelLane(_plot(qtbot), "cue", DARK_THEME, editable=False)
    lane.set_tier(Tier("cue", [Interval(1, 2, "1_x.wav")]))
    assert lane._pool[0].region.movable is False  # the recycled pool item for the visible interval


def test_trial_info_panel(qtbot):
    panel = TrialInfoPanel()
    qtbot.addWidget(panel)
    picked: list = []
    panel.error_code_picked.connect(picked.append)
    panel.set_trial(TrialInfo(3, 4.0, 5.0, "Yes/No", "casef.wav"))
    assert panel._values["Trial"].text() == "3"
    assert panel._values["Task"].text() == "Yes/No"
    assert panel._values["Stim"].text() == "casef.wav"
    panel.findChildren(QPushButton)[0].click()
    assert picked and picked[0] == "ERR_TASK_YN_REP"


def test_editor_set_tiers_and_selection(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    cue = Tier("cue_events", [Interval(4, 5, "1_jural.wav"), Interval(10, 11, "2_basin.wav")])
    cond = Tier("condition_events", [Interval(2, 2.5, "1_Yes/No"), Interval(8, 8.5, "2_Repeat")])
    ed.set_tiers(
        [
            ("cue_events", cue, False),
            ("condition_events", cond, False),
            ("response", Tier("response", []), True),
        ]
    )
    assert len(ed._label_lanes) == 3
    assert ed._focus_lane is not None and ed._focus_lane.name == "response"

    ed.set_selection((4.2, 4.8))
    assert ed._trial_panel._values["Trial"].text() == "1"
    assert ed._trial_panel._values["Stim"].text() == "jural.wav"

    ed._create_label_from_selection()  # Ctrl+B equivalent
    created = ed._focus_lane.intervals()
    assert len(created) == 1 and created[0].start == 4.2


def test_editor_tab_navigation(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(1, 2, "a"), Interval(5, 6, "b")]), True)])
    ed._navigate(1)
    assert ed.selection() == (1.0, 2.0)
    ed._navigate(1)
    assert ed.selection() == (5.0, 6.0)
