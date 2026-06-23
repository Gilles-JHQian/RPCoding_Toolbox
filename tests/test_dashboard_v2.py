"""Dashboard v0.2 widgets/behavior (offscreen). Skipped where PySide6/pytest-qt are absent."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import EffectiveState, Step
from rpcoding.core.tasks import Task
from rpcoding.gui.dashboard import Dashboard
from rpcoding.gui.theme import DARK_THEME
from rpcoding.gui.widgets.state_chip import StateChip
from rpcoding.gui.widgets.state_dot import StateDot
from rpcoding.gui.widgets.step_row import StepRow
from rpcoding.gui.widgets.subject_list import SubjectList


def test_state_chip_running_and_click_detail(qtbot):
    chip = StateChip(DARK_THEME)
    qtbot.addWidget(chip)
    chip.show()
    seen: list = []
    chip.clicked.connect(lambda: seen.append(1))

    chip.set_state(EffectiveState.DONE)  # no detail -> not clickable
    qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)
    assert seen == []

    chip.set_running()
    assert "Running" in chip.text()

    chip.set_state(EffectiveState.ERROR, detail="ValueError: boom")
    assert chip.toolTip() == "ValueError: boom"
    qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)
    assert seen == [1]


def test_state_dot_glyphs(qtbot):
    dot = StateDot(DARK_THEME)
    qtbot.addWidget(dot)
    dot.set_state(EffectiveState.DONE)
    assert dot.text() == "✓"
    dot.set_state(EffectiveState.ERROR)
    assert dot.text() == "!"
    dot.set_running()
    assert dot.text() == "●"


def test_step_row_error_rerunnable_and_detail(qtbot):
    row = StepRow(DARK_THEME, Step.CONCAT_WAVS, 2)
    qtbot.addWidget(row)
    got: list = []
    row.error_details.connect(got.append)
    row.set_state(EffectiveState.ERROR, meta="error", error="ValueError: boom")
    btn = row.findChild(QPushButton)
    assert "Re-run" in btn.text() and btn.isEnabled()  # error is re-runnable now
    row._chip.clicked.emit()
    assert got == [Step.CONCAT_WAVS]


def test_step_row_running_disables_button(qtbot):
    row = StepRow(DARK_THEME, Step.CONCAT_WAVS, 2)
    qtbot.addWidget(row)
    row.set_running()
    btn = row.findChild(QPushButton)
    assert not btn.isEnabled() and "Running" in btn.text()


def test_subject_list_summary_and_select(qtbot):
    sl = SubjectList(DARK_THEME)
    qtbot.addWidget(sl)
    sl.set_subjects(["D1", "D2"])
    sl.set_summary("D1", 7, 9, EffectiveState.STALE)
    assert sl._rows["D1"]._prog.text() == "7/9"
    assert set(sl.checked_subjects()) == {"D1", "D2"}

    got: list = []
    sl.subject_selected.connect(got.append)
    sl._rows["D2"].clicked.emit()
    assert got == ["D2"]


def _make_subject_dir(tmp_path, task, subject):
    (paths.d_data_dir(tmp_path, task) / subject).mkdir(parents=True)


def test_dashboard_task_switch_rescans(qtbot, tmp_path):
    _make_subject_dir(tmp_path, Task.LEXICAL_NODELAY, "D1")
    _make_subject_dir(tmp_path, Task.LEXICAL_DELAY, "D2")
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._scan()
    assert dash._subjects.count() == 1 and "D1" in dash._subjects._rows

    dash._task_combo.setCurrentIndex(1)  # -> LexicalDecRepDelay, auto-rescans
    assert dash._subjects.count() == 1 and "D2" in dash._subjects._rows


def test_dashboard_file_based_progress(qtbot, tmp_path):
    cfg = AppConfig(droot=tmp_path)
    s = SubjectSession(cfg, Task.LEXICAL_NODELAY, "D1")
    s.results_dir.mkdir(parents=True)
    (s.results_dir / paths.ALLBLOCKS_WAV).write_bytes(b"x")
    _make_subject_dir(tmp_path, Task.LEXICAL_NODELAY, "D1")
    dash = Dashboard(cfg, DARK_THEME)
    qtbot.addWidget(dash)
    dash._scan()
    # summaries fill in asynchronously (one per event-loop tick); create-results + concat -> 2/9
    qtbot.waitUntil(lambda: dash._subjects._rows["D1"]._prog.text() == "2/9", timeout=3000)


def test_dashboard_manual_step_opens_editor(qtbot, tmp_path):
    _make_subject_dir(tmp_path, Task.LEXICAL_NODELAY, "D1")
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._scan()
    dash._on_subject("D1")
    got: list = []
    dash.open_editor.connect(lambda _s, step: got.append(step))
    dash._on_step_action(Step.MARK_FIRST_STIMS)
    assert got == [Step.MARK_FIRST_STIMS]
