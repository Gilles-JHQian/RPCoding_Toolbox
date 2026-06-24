"""Label-track editing tests (offscreen). Skipped where PySide6/pyqtgraph aren't installed."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
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


def test_label_select_at_and_movable(qtbot):
    lane = LabelLane(_plot(qtbot), "response", DARK_THEME, editable=True)
    lane.set_tier(Tier("response", [Interval(0.2, 0.4, "a"), Interval(0.6, 0.9, "b")]))
    lane.set_view(0.0, 1.0, 800)
    # not selected -> not draggable
    assert all(it.region.movable is False for it in lane._pool[: lane._used])
    # click inside "b" selects it and makes only it draggable
    assert lane.select_at(0.75).label == "b"
    assert lane.active_interval().label == "b"
    sel = next(it for it in lane._pool[: lane._used] if it.idx == lane._active)
    assert sel.region.movable is True
    # clicking a gap deselects
    assert lane.select_at(0.5) is None
    assert lane.active_interval() is None


def test_editor_label_select_highlights_and_renames(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(2, 4, "1_no")]), True)])
    resp = ed._focus_lane

    ed._select_only(resp)
    resp.select_at(3.0)  # select the label under t=3
    assert ed._active_lane is resp
    assert ed.selection() == (2.0, 4.0)  # its span is highlighted across lanes

    ed._on_error_code("ERR_RESP_YN_NY")  # error palette appends the code
    assert resp.active_interval().label == "1_no/ERR_RESP_YN_NY"


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


def test_tab_key_navigates_labels(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(1, 2, "a"), Interval(5, 6, "b")]), True)])
    # event() intercepts Tab before focus traversal -> label navigation
    ed.event(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier))
    assert ed.selection() == (1.0, 2.0)
    ed.event(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier))
    assert ed.selection() == (5.0, 6.0)


def test_selection_move_vs_new(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    ed._on_region_dragged(10.0, 20.0, True)  # drag outside any selection -> new
    assert ed.selection() == (10.0, 20.0)
    ed._on_region_dragged(15.0, 25.0, True)  # drag starting inside [10,20] -> move by +10
    assert ed.selection() == (20.0, 30.0)
    ed._on_region_dragged(50.0, 60.0, True)  # drag starting outside -> new
    assert ed.selection() == (50.0, 60.0)


def test_audio_click_sets_cursor(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    ed.set_cursor(7.5)
    assert ed._cursor_master.value() == 7.5
    ed.set_selection((1.0, 2.0))  # a span supersedes the cursor
    assert ed.selection() == (1.0, 2.0)


def test_play_range_priority(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    assert ed._play_range() == (0.0, None)  # nothing -> whole file
    ed.set_cursor(5.0)
    assert ed._play_range() == (5.0, None)  # cursor -> to end
    ed.set_selection((10.0, 20.0))
    assert ed._play_range() == (10.0, 20.0)  # a selection wins -> play that span


def test_toggle_play_without_audio_is_noop(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    ed._toggle_play()  # no wav loaded -> must not raise or start
    assert not ed._player.is_playing()


def test_editable_selection_readout(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_selection((1.0, 2.0))
    assert ed._toolbar._sel_start.text() == "1.000"
    assert ed._toolbar._sel_end.text() == "2.000"
    # typing a precise start/end updates the selection
    ed._toolbar._sel_start.setText("3.5")
    ed._toolbar._sel_end.setText("4.25")
    ed._toolbar._emit_selection_edit()
    assert ed.selection() == (3.5, 4.25)


def test_clipboard_copy_paste(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(2, 4, "x")]), True)])
    resp = ed._focus_lane
    ed._select_only(resp)
    resp.select_at(3.0)
    ed._copy_active()
    assert ed._clipboard.label == "x"
    ed.set_cursor(10.0)
    ed._paste()  # paste at the cursor, preserving duration
    pasted = [iv for iv in resp.intervals() if iv.start == 10.0]
    assert pasted and pasted[0].end == 12.0 and pasted[0].label == "x"


def test_clipboard_cut(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(2, 4, "x")]), True)])
    resp = ed._focus_lane
    ed._select_only(resp)
    resp.select_at(3.0)
    ed._cut_active()
    assert ed._clipboard.label == "x" and resp.intervals() == []


def test_undo_redo(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    resp = ed._focus_lane
    ed.set_selection((1.0, 2.0))
    ed._create_label_from_selection()
    assert len(resp.intervals()) == 1
    ed._undo()
    assert resp.intervals() == []
    ed._redo()
    assert len(resp.intervals()) == 1


def test_resize_selection_region(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", []), True)])
    ed.set_selection((5.0, 10.0))
    ed._sel_master.setRegion((5.0, 15.0))  # drag an edge -> resize -> model follows
    assert ed.selection() == (5.0, 15.0)


def test_label_drag_updates_highlight_live(qtbot):
    ed = AudioEditor(DARK_THEME)
    qtbot.addWidget(ed)
    ed.set_tiers([("response", Tier("response", [Interval(2, 4, "x")]), True)])
    resp = ed._focus_lane
    resp.set_view(0.0, 10.0, 800)
    ed._select_only(resp)
    resp.select_at(3.0)
    assert ed.selection() == (2.0, 4.0)
    item = next(it for it in resp._pool[: resp._used] if it.idx == resp._active)
    item.region.setRegion((5.0, 7.0))  # mid-drag region change -> highlight follows live
    assert ed.selection() == (5.0, 7.0)
