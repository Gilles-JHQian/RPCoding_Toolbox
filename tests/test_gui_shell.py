"""GUI shell tests (offscreen). Skipped where PySide6 / pytest-qt aren't installed (e.g. CI)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QPushButton

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.steps import EffectiveState, Step
from rpcoding.core.tasks import Task
from rpcoding.gui.dashboard import Dashboard
from rpcoding.gui.main_window import MainWindow
from rpcoding.gui.theme import DARK_THEME, LIGHT_THEME, qss
from rpcoding.gui.widgets.step_row import StepRow
from rpcoding.gui.widgets.subject_list import SubjectList
from rpcoding.gui.workers.worker import Worker, run_in_thread


def test_theme_qss_and_state_colors():
    s = qss(DARK_THEME)
    assert "#4d96ff" in s  # accent present in the stylesheet
    assert DARK_THEME.state_color(EffectiveState.DONE) == "#46b771"
    assert LIGHT_THEME.state_color(EffectiveState.ERROR) == "#d23b32"


def test_excepthook_shows_dialog_instead_of_crashing(monkeypatch):
    import sys

    import rpcoding.gui.error_dialog as ed

    shown: list = []
    monkeypatch.setattr(ed, "show_error", lambda *a, **k: shown.append((a, k)))
    old = sys.excepthook
    try:
        ed.install_excepthook()
        try:
            raise ValueError("boom-xyz")
        except ValueError:
            sys.excepthook(*sys.exc_info())  # what PySide6 calls on an uncaught slot exception
        # the hook surfaced a dialog (with the traceback) and did NOT re-raise / abort
        assert shown and "boom-xyz" in shown[0][0][1]
    finally:
        sys.excepthook = old


def test_worker_emits_result():
    got: list = []
    w = Worker(lambda x: x * 2, 21)
    w.result.connect(got.append)
    w.run()
    assert got == [42]


def test_worker_emits_error():
    def boom():
        raise ValueError("nope")

    errs: list = []
    w = Worker(boom)
    w.error.connect(errs.append)
    w.run()
    assert errs and "nope" in errs[0]


def test_run_in_thread(qtbot):
    parent = QObject()
    results: list = []
    run_in_thread(parent, lambda: 7, on_result=results.append)
    qtbot.waitUntil(lambda: results == [7], timeout=3000)


def test_subject_list(qtbot):
    sl = SubjectList()
    qtbot.addWidget(sl)
    sl.set_subjects(["D9", "D10"])
    assert sl.count() == 2
    assert set(sl.checked_subjects()) == {"D9", "D10"}


def test_step_row_states(qtbot):
    row = StepRow(DARK_THEME, Step.CONCAT_WAVS, 2)
    qtbot.addWidget(row)
    row.set_state(EffectiveState.DONE)
    assert "Re-run" in row.findChild(QPushButton).text()

    manual = StepRow(DARK_THEME, Step.MARK_FIRST_STIMS, 5)
    qtbot.addWidget(manual)
    manual.set_state(EffectiveState.NEEDS_MANUAL)
    assert manual.findChild(QPushButton).text() == "Open editor"


def test_dashboard_scan(qtbot, tmp_path):
    dd = paths.d_data_dir(tmp_path, Task.LEXICAL_NODELAY)
    (dd / "D9").mkdir(parents=True)
    (dd / "D10").mkdir()
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._task_combo.setCurrentIndex(0)  # LexicalDecRepNoDelay
    dash._scan()
    assert dash._subjects.count() == 2


def test_main_window_theme_toggle(qtbot, tmp_path):
    win = MainWindow(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(win)
    assert win._theme.name == "dark"
    win.toggle_theme()
    assert win._theme.name == "light"
