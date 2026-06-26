"""Tests for the loading dialog + the app-wide hover-cursor filter."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QLabel, QPushButton

from rpcoding.gui.hover_cursor import HoverCursorFilter
from rpcoding.gui.loading_dialog import LoadingDialog


def test_hover_cursor_sets_pointing_hand_on_buttons(qtbot):
    btn = QPushButton("x")
    qtbot.addWidget(btn)
    filt = HoverCursorFilter()
    filt.eventFilter(btn, QEvent(QEvent.Type.Enter))
    assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor
    btn.setEnabled(False)
    filt.eventFilter(btn, QEvent(QEvent.Type.Enter))
    assert btn.cursor().shape() == Qt.CursorShape.ArrowCursor  # disabled -> plain arrow


def test_hover_cursor_ignores_non_clickable(qtbot):
    lbl = QLabel("x")
    qtbot.addWidget(lbl)
    before = lbl.cursor().shape()
    HoverCursorFilter().eventFilter(lbl, QEvent(QEvent.Type.Enter))
    assert lbl.cursor().shape() == before  # labels are left alone


def test_loading_dialog_progress_and_busy(qtbot):
    dlg = LoadingDialog("Loading…")
    qtbot.addWidget(dlg)
    dlg.set_progress(40, "halfway")
    assert (dlg._bar.minimum(), dlg._bar.maximum()) == (0, 100)
    assert dlg._bar.value() == 40
    assert dlg._status.text() == "halfway"
    dlg.set_busy("working")
    assert dlg._bar.maximum() == 0  # indeterminate (animated) bar
