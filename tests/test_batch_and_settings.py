"""Settings + batch dialog behavior (offscreen). Skipped where PySide6 is absent."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from rpcoding.core.config import AppConfig
from rpcoding.core.tasks import Task
from rpcoding.gui.batch_dialog import BatchDialog
from rpcoding.gui.clock_fix import ClockFixDialog
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
    assert out.mfa_task(Task.UNIQUENESS_POINT) == "uniqueness_point"


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


def test_settings_fix_clock_returns_custom_code(qtbot, tmp_path):
    dlg = SettingsDialog(AppConfig(droot=tmp_path))
    qtbot.addWidget(dlg)
    dlg.done(SettingsDialog.FIX_CLOCK)  # what the "Fix clock drift" button does
    assert dlg.result() == SettingsDialog.FIX_CLOCK == 2


def test_clock_fix_dialog_lists_subjects(qtbot, tmp_path):
    # two UP subjects on disk -> the picker should offer them for the UP task
    for s in ("D28", "D42"):
        (tmp_path / "D_Data" / "Uniqueness_Point" / s).mkdir(parents=True)
    dlg = ClockFixDialog(AppConfig(droot=tmp_path), default_task=Task.UNIQUENESS_POINT)
    qtbot.addWidget(dlg)
    assert dlg.task == Task.UNIQUENESS_POINT
    assert {dlg._subject.itemText(i) for i in range(dlg._subject.count())} == {"D28", "D42"}
    assert dlg.subject in ("D28", "D42")


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


def test_batch_dialog_stop_button(qtbot, tmp_path):
    dlg = BatchDialog(AppConfig(droot=tmp_path), Task.LEXICAL_NODELAY, ["D100", "D101"])
    qtbot.addWidget(dlg)
    assert dlg._run.isEnabled() and not dlg._stop.isEnabled()  # idle: Run on, Stop off
    dlg._running = True  # pretend a run is in flight (without launching a thread)
    dlg._stop.setEnabled(True)
    dlg._request_stop()
    assert dlg._cancel.is_set()  # the worker's should_cancel will now return True
    assert not dlg._stop.isEnabled()
    assert "Stopping" in dlg._overall_label.text()


def test_batch_dialog_finish_after_stop_marks_remaining(qtbot, tmp_path):
    dlg = BatchDialog(AppConfig(droot=tmp_path), Task.LEXICAL_NODELAY, ["D100", "D101"])
    qtbot.addWidget(dlg)
    dlg._running = True
    dlg._cancel.set()
    dlg._on_subject_done("D100", "ok", "[]")  # first subject ran before the stop took effect
    dlg._on_finished()
    assert dlg._table.item(1, 1).text() == "— stopped"  # D101 never started
    assert "Stopped" in dlg._overall_label.text()
    assert dlg._run.isEnabled() and not dlg._stop.isEnabled()


def test_merge_multipart_dialog_merges(qtbot, tmp_path):
    import numpy as np
    import scipy.io as sio

    from rpcoding.core import paths
    from rpcoding.gui.multipart_merge import MergeMultipartDialog

    droot = tmp_path / "CoganLab"
    subj_dir = paths.d_data_subject_dir(droot, Task.LEXICAL_NODELAY, "D9")
    dm = subj_dir / "230101" / "mat"
    dm.mkdir(parents=True)
    (subj_dir / "mat").mkdir(parents=True)

    def _save(path, var, n):
        arr = np.zeros((1, n), dtype=[("Trial", "O")])
        for i in range(n):
            arr[0, i]["Trial"] = i + 1
        sio.savemat(str(path), {var: arr})

    _save(dm / "Trials1.mat", "Trials", 3)
    _save(dm / "Trials2.mat", "Trials", 4)
    _save(dm / "trialInfo1.mat", "trialInfo", 3)
    _save(dm / "trialInfo2.mat", "trialInfo", 4)
    sio.savemat(str(subj_dir / "mat" / "experiment1.mat"), {"experiment": np.array([[1.0]])})
    sio.savemat(str(subj_dir / "mat" / "experiment2.mat"), {"experiment": np.array([[1.0]])})

    dlg = MergeMultipartDialog(
        AppConfig(droot=droot), default_task=Task.LEXICAL_NODELAY, default_subject="D9"
    )
    qtbot.addWidget(dlg)
    assert dlg._subject.currentText() == "D9"  # defaulted to the passed subject
    dlg._do_merge()
    assert (dm / "Trials.mat").exists() and (dm / "trialInfo.mat").exists()
    assert (subj_dir / "mat" / "experiment.mat").exists()
    assert "merged" in dlg._out.toPlainText()
    assert sio.loadmat(str(dm / "Trials.mat"))["Trials"].shape[1] == 7  # 3 + 4
