"""Tests for .mat I/O and trialInfo normalization."""

from __future__ import annotations

import numpy as np
import scipy.io as sio

from rpcoding.core import matio


def _save_cell_of_structs(path, trials):
    """Write trialInfo as a 1xN MATLAB cell array of structs."""
    arr = np.empty((1, len(trials)), dtype=object)
    for i, t in enumerate(trials):
        arr[0, i] = t
    sio.savemat(str(path), {"trialInfo": arr})


def _save_struct_array(path, fields, rows):
    """Write trialInfo as a 1xN MATLAB struct array."""
    rec = np.zeros((1, len(rows)), dtype=[(f, "O") for f in fields])
    for i, row in enumerate(rows):
        rec[0, i] = tuple(row)
    sio.savemat(str(path), {"trialInfo": rec})


def test_load_trialinfo_cell_of_structs(tmp_path):
    p = tmp_path / "ti.mat"
    _save_cell_of_structs(
        p,
        [
            {"block": 1.0, "cue": "Yes/No", "sound": "casef.wav"},
            {"block": 1.0, "cue": "Repeat", "sound": "galef.wav"},
        ],
    )
    ti = matio.load_trialinfo(p)
    assert isinstance(ti, list) and len(ti) == 2
    assert ti[0]["sound"] == "casef.wav"
    assert matio.trial_cue(ti[1]) == "Repeat"
    assert matio.trial_block(ti[0]) == 1.0


def test_load_trialinfo_struct_array(tmp_path):
    p = tmp_path / "sa.mat"
    _save_struct_array(
        p,
        ["block", "cue", "sound"],
        [(1.0, "Yes/No", "casef.wav"), (2.0, "Repeat", "galef.wav")],
    )
    ti = matio.load_trialinfo(p)
    assert len(ti) == 2
    assert ti[1]["block"] == 2.0
    assert matio.trial_stim(ti[1]) == "galef.wav"


def test_field_ladders_fallbacks(tmp_path):
    p = tmp_path / "ti.mat"
    _save_cell_of_structs(
        p,
        [{"block": 1.0, "condition": "Repeat", "stim": "x.wav", "stimulusAudioStart": 3.5}],
    )
    t = matio.load_trialinfo(p)[0]
    assert matio.trial_stim(t) == "x.wav"  # falls back to 'stim'
    assert matio.trial_cue(t) == "Repeat"  # falls back to 'condition'
    assert matio.trial_audio_onset(t) == 3.5  # third name in the ladder


def test_missing_variable_raises(tmp_path):
    p = tmp_path / "x.mat"
    matio.save_mat(p, {"other": np.array([1.0])})
    import pytest

    with pytest.raises(KeyError):
        matio.load_trialinfo(p)


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "x.mat"
    matio.save_mat(p, {"A": np.array([1.0, 2.0, 3.0])})
    assert list(matio.load_mat(p)["A"].ravel()) == [1.0, 2.0, 3.0]
