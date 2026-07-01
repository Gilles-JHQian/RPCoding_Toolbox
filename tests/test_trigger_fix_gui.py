"""TriggerFixDialog behavior + a synthetic end-to-end analyze/apply (offscreen).

Skipped where PySide6 / pyqtgraph aren't installed.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.matio import save_mat
from rpcoding.core.rpcode.rpcode2trials import save_trials
from rpcoding.core.tasks import Task
from rpcoding.gui.settings_dialog import SettingsDialog
from rpcoding.gui.trigger_fix import TriggerFixDialog

FREQ = 2048.0
CONST = 5.0  # experiment-clock -> EDF-clock offset (s)
GAP = 2.0  # cue -> stimulus gap (s)


def _save_records(path, var, records):
    fields = list(records[0])
    arr = np.empty((1, len(records)), dtype=[(f, object) for f in fields])
    for i, r in enumerate(records):
        for f in fields:
            arr[0, i][f] = r[f]
    save_mat(path, {var: arr})


def _make_subject(droot, task, subj, *, misalign=True):
    """Write a minimal 2-block × 4-trial subject: trialInfo + trigger.mat + (misaligned) Trials.mat
    + first_stims, so the dialog can analyze and apply."""
    audio = np.array([10.0, 14.0, 18.0, 22.0, 40.0, 44.0, 48.0, 52.0])
    blocks = [1, 1, 1, 1, 2, 2, 2, 2]
    edf_stim = audio - CONST
    edf_cue = edf_stim - GAP

    results_dir = paths.results_dir(droot, task, subj)
    results_dir.mkdir(parents=True, exist_ok=True)
    trialinfo = [
        {
            "stimulusAudioStart": float(audio[i]),
            "cueStart": float(audio[i] - GAP),
            "block": float(blocks[i]),
            "sound": f"w{i}",
            "cue": "Yes/No",
        }
        for i in range(len(audio))
    ]
    _save_records(results_dir / paths.TRIALINFO_MAT, "trialInfo", trialinfo)
    write_tier(
        Tier("first_stims", [Interval(10.0, 11.0, "b1"), Interval(40.0, 41.0, "b2")]),
        results_dir / paths.FIRST_STIMS_TXT,
    )

    d_dir = paths.d_data_subject_dir(droot, task, subj) / "mat"
    d_dir.mkdir(parents=True, exist_ok=True)
    trig = np.full(int(60 * FREQ), 100.0)
    for t in np.concatenate([edf_cue, edf_stim]):
        s = int(t * FREQ)
        trig[s : s + 20] = 1000.0
    save_mat(d_dir / "trigger.mat", {"trigger": trig})

    bad = edf_stim.copy()
    if misalign:
        bad[2:4] += 2.0  # a block-1 step: trials 3-4 read off their true pulse
    trials = [
        {"Auditory": float(bad[i] * 3e4), "Start": float(bad[i] * 3e4 - 3e4), "Trial": i + 1}
        for i in range(len(audio))
    ]
    save_trials(d_dir / "Trials.mat", trials)
    return results_dir, d_dir / "Trials.mat", edf_stim


def test_settings_fix_trigger_returns_custom_code(qtbot, tmp_path):
    dlg = SettingsDialog(AppConfig(droot=tmp_path))
    qtbot.addWidget(dlg)
    dlg.done(SettingsDialog.FIX_TRIGGER)
    assert dlg.result() == SettingsDialog.FIX_TRIGGER == 4


def test_dialog_lists_subjects(qtbot, tmp_path):
    for s in ("D90", "D139"):
        paths.d_data_subject_dir(tmp_path, Task.LEXICAL_NODELAY, s).mkdir(parents=True)
    dlg = TriggerFixDialog(AppConfig(droot=tmp_path), default_task=Task.LEXICAL_NODELAY)
    qtbot.addWidget(dlg)
    assert {dlg._subject.itemText(i) for i in range(dlg._subject.count())} == {"D90", "D139"}
    assert not dlg._thr.isEnabled()  # nothing analyzed yet
    assert not dlg._apply.isEnabled()


def test_analyze_then_apply_fixes_misalignment(qtbot, tmp_path, monkeypatch):
    task, subj = Task.LEXICAL_NODELAY, "D90"
    results_dir, trials_path, edf_stim = _make_subject(tmp_path, task, subj, misalign=True)
    dlg = TriggerFixDialog(AppConfig(droot=tmp_path), default_task=task, default_subject=subj)
    qtbot.addWidget(dlg)

    dlg._do_analyze()
    assert dlg._loaded is not None
    assert dlg._thr.isEnabled()
    assert dlg._apply.isEnabled()  # re-derivation beats the misaligned current file
    assert "MISALIGNED" not in dlg._out.toPlainText().splitlines()[-1]

    # exercise the real Apply button path with the confirm auto-accepted
    from rpcoding.core.matio import load_trials
    from rpcoding.gui import trigger_fix as tf_mod

    monkeypatch.setattr(
        tf_mod.QMessageBox, "question",
        lambda *a, **k: tf_mod.QMessageBox.StandardButton.Yes,
    )
    dlg._do_apply()
    assert not dlg._apply.isEnabled()  # applied

    # the correction lands in D_Data (in place), original backed up; results dir is NOT used
    assert not (results_dir / paths.TRIALS_MAT).exists()
    assert trials_path.with_name("Trials.mat.before_trigger_fix").exists()
    fixed = np.array([float(t["Auditory"]) / 3e4 for t in load_trials(trials_path)])
    assert fixed == pytest.approx(edf_stim, abs=0.05)  # D_Data Auditory now on the true grid

    # regenerated cue_events now line up (block-relative) with the true stimulus grid
    cue = [iv.start for iv in read_tier(results_dir / paths.CUE_EVENTS_TXT)]
    assert len(cue) == 8
    # block 1 spacing follows the true EDF stimulus spacing, not the corrupted one
    assert cue[1] - cue[0] == pytest.approx(edf_stim[1] - edf_stim[0], abs=0.05)
    assert cue[3] - cue[2] == pytest.approx(edf_stim[3] - edf_stim[2], abs=0.05)


def test_subject_change_resets_state(qtbot, tmp_path):
    task = Task.LEXICAL_NODELAY
    _make_subject(tmp_path, task, "D90", misalign=True)
    paths.d_data_subject_dir(tmp_path, task, "D139").mkdir(parents=True, exist_ok=True)
    dlg = TriggerFixDialog(AppConfig(droot=tmp_path), default_task=task, default_subject="D90")
    qtbot.addWidget(dlg)
    dlg._do_analyze()
    assert dlg._loaded is not None
    dlg._subject.setCurrentText("D139")  # switch subjects
    assert dlg._loaded is None
    assert not dlg._thr.isEnabled()
    assert not dlg._apply.isEnabled()
