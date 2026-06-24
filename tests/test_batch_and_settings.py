"""Settings + batch dialog behavior (offscreen). Skipped where PySide6 is absent."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from rpcoding.core.config import AppConfig
from rpcoding.core.tasks import Task
from rpcoding.gui.batch_dialog import BatchDialog
from rpcoding.gui.settings_dialog import SettingsDialog


def test_settings_roundtrip(qtbot, tmp_path):
    cfg = AppConfig(
        droot=tmp_path / "CoganLab",
        word_list=tmp_path / "word_lst.mat",
        nonword_list=tmp_path / "nonword_lst.mat",
    )
    dlg = SettingsDialog(cfg)
    qtbot.addWidget(dlg)
    out = dlg.result_config()
    assert out.droot == tmp_path / "CoganLab"
    assert out.word_list == tmp_path / "word_lst.mat"
    assert out.nonword_list == tmp_path / "nonword_lst.mat"
    # default task map preserved
    assert out.mfa_task(Task.LEXICAL_NODELAY) == "lexical_repeat_no_delay"
    assert out.mfa_task(Task.UNIQUENESS_POINT) is None


def test_settings_edit_word_list_and_task(qtbot, tmp_path):
    dlg = SettingsDialog(AppConfig(droot=tmp_path))
    qtbot.addWidget(dlg)
    dlg._word._edit.setText(str(tmp_path / "w.mat"))
    dlg._mfa[Task.UNIQUENESS_POINT.value].setText("uniqueness_cfg")
    out = dlg.result_config()
    assert out.word_list == tmp_path / "w.mat"
    assert out.mfa_task(Task.UNIQUENESS_POINT) == "uniqueness_cfg"


def test_settings_blank_word_list_is_none(qtbot, tmp_path):
    dlg = SettingsDialog(AppConfig(droot=tmp_path))
    qtbot.addWidget(dlg)
    assert dlg.result_config().word_list is None


def test_settings_dialog_has_mfa_panel(qtbot, tmp_path):
    dlg = SettingsDialog(AppConfig(droot=tmp_path))
    qtbot.addWidget(dlg)
    assert dlg._mfa_install_btn.text() in ("Download & install models", "Re-install / repair")
    assert dlg._mfa_status_lay.count() >= 4  # one status row per probed item


def test_settings_editor_audio_choice_roundtrip(qtbot, tmp_path):
    dlg = SettingsDialog(AppConfig(droot=tmp_path, editor_use_processed_audio=True))
    qtbot.addWidget(dlg)
    assert dlg._use_processed.isChecked()  # reflects the config
    dlg._use_processed.setChecked(False)
    assert dlg.result_config().editor_use_processed_audio is False


def test_batch_dialog_rows_and_progress(qtbot, tmp_path):
    dlg = BatchDialog(AppConfig(droot=tmp_path), Task.LEXICAL_NODELAY, ["D100", "D101"])
    qtbot.addWidget(dlg)
    assert dlg._table.rowCount() == 2
    scale = dlg._bar.maximum()  # fine-grained footer bar

    dlg._on_subject_done("D100", "ok", "[]")
    assert dlg._table.item(0, 1).text() == "✓ ran"
    assert dlg._bar.value() == scale // 2  # 1 of 2 subjects done

    dlg._on_subject_done("D101", "error", "RuntimeError: boom")
    assert "boom" in dlg._table.item(1, 1).text()
    assert dlg._bar.value() == scale


def test_batch_dialog_step_progress(qtbot, tmp_path):
    dlg = BatchDialog(AppConfig(droot=tmp_path), Task.LEXICAL_NODELAY, ["D100", "D101"])
    qtbot.addWidget(dlg)
    scale = dlg._bar.maximum()
    # A mid-step tick updates that subject's row text + per-row bar, and the overall bar.
    dlg._on_step_tick("D100", "Concatenate WAVs → allblocks.wav", 0.5, "Reading block 3…", 0.4)
    assert "Concatenate" in dlg._table.item(0, 1).text()
    bar = dlg._bars["D100"]
    assert (bar.minimum(), bar.maximum()) == (0, 100)
    assert bar.value() == 50
    # overall = (0 done + 0.4 within-pipeline) / 2 subjects
    assert dlg._bar.value() == round(0.4 / 2 * scale)

    # Indeterminate tick -> the per-row bar goes busy.
    dlg._on_step_tick("D100", "MFA forced alignment", None, "Running forced alignment…", 0.6)
    assert dlg._bars["D100"].maximum() == 0
