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
    # summaries fill in asynchronously (one per event-loop tick); create-results + concat -> 2/8
    # (8 required steps; the optional Denoise is excluded from the count)
    qtbot.waitUntil(lambda: dash._subjects._rows["D1"]._prog.text() == "2/8", timeout=3000)
    # …and the row shows the current step it's at (next required step = build trialInfo)
    assert dash._subjects._rows["D1"]._step.text() == "trialInfo"


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


def test_dashboard_notes_and_flag(qtbot, tmp_path):
    _make_subject_dir(tmp_path, Task.LEXICAL_NODELAY, "D1")
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._scan()
    dash._on_subject("D1")
    assert dash._notes.isEnabled() and dash._notes.toPlainText() == ""
    assert not dash._flag_btn.isChecked()

    dash._notes.setPlainText("noisy block 3")
    dash._save_notes()  # the debounce timer's slot, called directly
    assert dash._session.notes == "noisy block 3"

    dash._flag_btn.setChecked(True)  # toggled -> _on_flag_toggled
    assert dash._session.flagged is True
    assert dash._session.summary()[2] == EffectiveState.FLAGGED

    dash._on_subject("D1")  # reselect reloads the saved notes + flag
    assert dash._notes.toPlainText() == "noisy block 3"
    assert dash._flag_btn.isChecked()


def test_data_root_dialog_requires_a_choice(qtbot):
    from rpcoding.gui.first_run_dialog import DataRootDialog

    dlg = DataRootDialog()
    qtbot.addWidget(dlg)
    assert dlg.chosen_path() is None
    assert not dlg._ok.isEnabled()  # can't proceed until a folder is chosen


def test_subject_count_format_and_selection(qtbot, tmp_path):
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._subjects.set_subjects(["D1", "D2", "D3"])
    dash._update_count()
    assert dash._subj_count.text() == "3 found · 3 selected"
    dash._subjects._rows["D1"].check.setChecked(False)  # toggling updates the count live
    assert dash._subj_count.text() == "3 found · 2 selected"


def test_subject_filter_and_add_remove(qtbot, tmp_path):
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._subjects.set_subjects(["D12", "D14", "S03"])
    dash._filter.setText("d1")
    assert dash._subjects._items["S03"].isHidden()
    assert not dash._subjects._items["D12"].isHidden()
    dash._filter.setText("D99")
    dash._add_subject()
    assert "D99" in dash._subjects._rows and dash._filter.text() == ""
    dash._subjects.setCurrentItem(dash._subjects._items["D99"])
    dash._remove_subject()
    assert "D99" not in dash._subjects._rows


def test_save_and_restore_subject_list(qtbot, tmp_path, monkeypatch):
    import rpcoding.gui.config as gcfg

    monkeypatch.setattr(gcfg, "config_dir", lambda: tmp_path)
    for sid in ("D1", "D2", "D3"):
        _make_subject_dir(tmp_path, Task.LEXICAL_NODELAY, sid)
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._scan()
    dash._subjects.set_checked(["D2"])
    dash._save_list()
    dash._scan()  # rescans and restores the saved selection
    assert dash._subjects.checked_subjects() == ["D2"]


def test_select_all_toggle(qtbot, tmp_path):
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._subjects.set_subjects(["D1", "D2", "D3"])
    dash._update_count()
    assert dash._select_all.checkState() == Qt.CheckState.Checked  # all checked by default
    dash._toggle_all()  # all -> none
    assert dash._subjects.selected_count() == 0
    assert dash._select_all.checkState() == Qt.CheckState.Unchecked
    dash._toggle_all()  # none -> all
    assert dash._subjects.selected_count() == 3
    dash._subjects._rows["D2"].check.setChecked(False)  # partial
    assert dash._select_all.checkState() == Qt.CheckState.PartiallyChecked
    dash._toggle_all()  # partial -> all
    assert dash._subjects.selected_count() == 3


def test_qss_label_background_transparent():
    from rpcoding.gui.theme import LIGHT_THEME, qss

    # Plain labels must be transparent so they don't paint an app-bg box over a coloured parent.
    for theme in (DARK_THEME, LIGHT_THEME):
        assert "QLabel { background: transparent" in qss(theme)


def test_step_row_manual_tag_and_mono_filename(qtbot):
    manual = StepRow(DARK_THEME, Step.MARK_FIRST_STIMS, 5)
    qtbot.addWidget(manual)
    assert manual._manual and manual._manual_tag.isVisibleTo(manual)
    assert "first_stims.txt" in manual._name.text() and "font-family" in manual._name.text()
    auto = StepRow(DARK_THEME, Step.CREATE_RESULTS, 1)
    qtbot.addWidget(auto)
    assert not auto._manual and not auto._manual_tag.isVisibleTo(auto)
