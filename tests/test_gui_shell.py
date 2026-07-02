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


def test_run_in_thread_callbacks_run_on_main_thread(qtbot):
    # Regression: callbacks must fire on the GUI thread so they can touch widgets. A bare-closure
    # callback would otherwise run on the worker thread (direct connection) and a widget access
    # there hard-crashes Qt — this was the "app quits right after the last step finished" bug.
    import threading

    parent = QObject()
    main_tid = threading.get_ident()
    seen: dict[str, int] = {}
    run_in_thread(
        parent,
        lambda: 1,
        on_result=lambda _v: seen.__setitem__("result", threading.get_ident()),
        on_finished=lambda: seen.__setitem__("finished", threading.get_ident()),
    )
    qtbot.waitUntil(lambda: "finished" in seen, timeout=3000)
    assert seen["result"] == main_tid
    assert seen["finished"] == main_tid


def test_run_in_thread_error_callback_on_main_thread(qtbot):
    import threading

    def boom():
        raise RuntimeError("x")

    parent = QObject()
    main_tid = threading.get_ident()
    seen: dict[str, int] = {}
    run_in_thread(parent, boom, on_error=lambda _m: seen.__setitem__("tid", threading.get_ident()))
    qtbot.waitUntil(lambda: "tid" in seen, timeout=3000)
    assert seen["tid"] == main_tid


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


def test_step_row_inline_progress(qtbot):
    row = StepRow(DARK_THEME, Step.CONCAT_WAVS, 2)
    qtbot.addWidget(row)
    row.show()
    # Idle: the progress row is hidden, the meta line is shown.
    assert not row._prog_row.isVisibleTo(row)

    row.set_running()
    assert row._prog_row.isVisibleTo(row)
    assert not row._meta.isVisibleTo(row)
    assert row._progress.maximum() == 0  # indeterminate until the first real tick

    row.set_progress(0.5, "Reading block 3 (3/6)…")
    assert (row._progress.minimum(), row._progress.maximum()) == (0, 100)
    assert row._progress.value() == 50
    assert "block 3" in row._status.text()

    row.set_progress(None, "Merging…")  # indeterminate again
    assert row._progress.maximum() == 0

    # Finishing flips back to the static state; the bar hides.
    row.set_state(EffectiveState.DONE, "ran just now")
    assert not row._prog_row.isVisibleTo(row)
    assert row._meta.isVisibleTo(row)


def test_step_row_chip_and_button_aligned(qtbot):
    # Equal-width chip + action columns so the state column lines up across rows.
    a = StepRow(DARK_THEME, Step.CONCAT_WAVS, 2)
    b = StepRow(DARK_THEME, Step.MARK_FIRST_STIMS, 5)
    qtbot.addWidget(a)
    qtbot.addWidget(b)
    # Fixed widths line up regardless of layout pass (min == max == fixed).
    assert a._chip.maximumWidth() == b._chip.maximumWidth() == 112
    assert a.findChild(QPushButton).maximumWidth() == 112


def test_dashboard_scan(qtbot, tmp_path):
    dd = paths.d_data_dir(tmp_path, Task.LEXICAL_NODELAY)
    (dd / "D9").mkdir(parents=True)
    (dd / "D10").mkdir()
    dash = Dashboard(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(dash)
    dash._task_combo.setCurrentIndex(0)  # LexicalDecRepNoDelay
    dash._scan()  # lists subjects off the UI thread, so the rows arrive asynchronously
    qtbot.waitUntil(lambda: dash._subjects.count() == 2, timeout=3000)


def test_main_window_theme_toggle(qtbot, tmp_path):
    win = MainWindow(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(win)
    assert win._theme.name == "dark"
    win.toggle_theme()
    assert win._theme.name == "light"
    assert win._editor is None  # the editor is built lazily on first open, not at startup


def test_main_window_title_and_icon(qtbot, tmp_path):
    from rpcoding.gui.assets import ico_path, icon_path

    assert icon_path().exists() and ico_path().exists()  # the brain icon ships with the package
    win = MainWindow(AppConfig(droot=tmp_path), DARK_THEME)
    qtbot.addWidget(win)
    assert win.windowTitle() == "Cogan Lab RP Coding Toolbox"
    assert not win.windowIcon().isNull()  # loaded from the bundled asset


def test_app_import_does_not_pull_the_editor():
    # Lazy editor: importing the app must not load pyqtgraph / scipy.signal (~0.7s + 0.5s) — they
    # belong to the editor and are deferred to first open so startup stays fast. Run in a fresh
    # interpreter since other tests in this process import the editor.
    import subprocess
    import sys

    code = (
        "import rpcoding.gui.app, sys; "
        "print('pyqtgraph' in sys.modules, 'scipy.signal' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False False", out.stdout
