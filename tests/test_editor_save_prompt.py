"""Editor prompts to save unsaved edits on exit (Esc / Back / close). Offscreen; needs PySide6."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtGui import QCloseEvent

from rpcoding.core.labels import Tier
from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.editor import track_container as tc
from rpcoding.gui.theme import DARK_THEME

_Q = tc.QMessageBox.StandardButton


@pytest.fixture(autouse=True, scope="module")
def _safe_dialogs():
    # pytest-qt closes leftover widgets at teardown, which fires our save prompt — after per-test
    # monkeypatches are undone. Patch the dialog for the whole module (outliving those teardowns) so
    # a stray close can never block on a real, offscreen QMessageBox. Tests still override per-case.
    orig = tc.QMessageBox.question
    tc.QMessageBox.question = lambda *a, **k: _Q.Discard
    yield
    tc.QMessageBox.question = orig


@pytest.fixture
def ed(qtbot, tmp_path):
    e = AudioEditor(DARK_THEME)
    qtbot.addWidget(e)
    e.set_tiers([("response", Tier("response", []), True)])
    e.configure_save(tmp_path / "resp.txt")
    return e


def _make_edit(e) -> None:
    e.set_selection((3.0, 4.0))
    e._create_label_from_selection()  # add a label to the editable lane


def test_not_dirty_after_load(ed):
    assert not ed.is_dirty()


def test_dirty_after_edit(ed):
    _make_edit(ed)
    assert ed.is_dirty()


def test_clean_after_save(ed):
    _make_edit(ed)
    ed.save()
    assert not ed.is_dirty()


def test_confirm_save_writes_and_clears_dirty(ed, tmp_path, monkeypatch):
    _make_edit(ed)
    monkeypatch.setattr(tc.QMessageBox, "question", lambda *a, **k: _Q.Save)
    assert ed._confirm_discard_or_save() is True  # ok to close
    assert (tmp_path / "resp.txt").exists()  # it saved
    assert not ed.is_dirty()


def test_confirm_discard_does_not_save(ed, tmp_path, monkeypatch):
    _make_edit(ed)
    monkeypatch.setattr(tc.QMessageBox, "question", lambda *a, **k: _Q.Discard)
    assert ed._confirm_discard_or_save() is True  # ok to close
    assert not (tmp_path / "resp.txt").exists()  # discarded, nothing written


def test_confirm_cancel_keeps_open(ed, monkeypatch):
    _make_edit(ed)
    monkeypatch.setattr(tc.QMessageBox, "question", lambda *a, **k: _Q.Cancel)
    assert ed._confirm_discard_or_save() is False  # stay open


def test_close_event_when_clean_does_not_prompt(ed, monkeypatch):
    asked: list = []
    monkeypatch.setattr(tc.QMessageBox, "question", lambda *a, **k: asked.append(1) or _Q.Cancel)
    ev = QCloseEvent()
    ed.closeEvent(ev)
    assert asked == []  # nothing unsaved -> no prompt
    assert ev.isAccepted()


def test_close_event_cancel_ignores_event(ed, monkeypatch):
    _make_edit(ed)
    monkeypatch.setattr(tc.QMessageBox, "question", lambda *a, **k: _Q.Cancel)
    ev = QCloseEvent()
    ed.closeEvent(ev)
    assert not ev.isAccepted()  # cancelled -> editor stays open


def test_close_event_save_accepts_and_writes(ed, tmp_path, monkeypatch):
    _make_edit(ed)
    monkeypatch.setattr(tc.QMessageBox, "question", lambda *a, **k: _Q.Save)
    ev = QCloseEvent()
    ed.closeEvent(ev)
    assert ev.isAccepted() and (tmp_path / "resp.txt").exists()
