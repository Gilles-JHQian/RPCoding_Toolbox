"""Tests for trialInfo merge/build (combine_trialInfo / fix_trialInfo_blocks / cell2mat ports)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import scipy.io as sio

from rpcoding.core.matio import load_trialinfo
from rpcoding.core.trialinfo.build import (
    IncompleteTrialInfoError,
    build_trialinfo,
    discover_trialdata_files,
    save_trialinfo,
    select_and_combine,
)
from rpcoding.core.trialinfo.merge import (
    block_sequence,
    fix_trialinfo_blocks,
    homogenize_trials,
)

# Local real-data root (skipped in CI / where Box isn't synced).
_REAL = Path("F:/CloudStorage/Box/CoganLab/ECoG_Task_Data/Cogan_Task_Data")


def _save_trialdata(path, block_values):
    trials = [
        {"block": float(b), "cue": "Yes/No", "sound": f"s{i}.wav"}
        for i, b in enumerate(block_values)
    ]
    arr = np.empty((1, len(trials)), dtype=object)
    for i, t in enumerate(trials):
        arr[0, i] = t
    sio.savemat(str(path), {"trialInfo": arr})


def test_block_sequence():
    trials = [{"block": 1.0}, {"block": 1.0}, {"block": 2.0}, {"block": 2.0}]
    assert block_sequence(trials) == [1, 2]


def test_select_and_combine_split_run(tmp_path):
    # D140-like: two runs, each cumulative within itself
    _save_trialdata(tmp_path / "D9_Block_1_TrialData.mat", [1, 1, 1])
    _save_trialdata(tmp_path / "D9_Block_2_TrialData.mat", [1, 1, 1, 2, 2, 2])
    _save_trialdata(tmp_path / "D9_Block_3_TrialData.mat", [3, 3, 3])
    _save_trialdata(tmp_path / "D9_Block_4_TrialData.mat", [3, 3, 3, 4, 4, 4])
    files = discover_trialdata_files(tmp_path)
    combined, info = select_and_combine(files)

    assert block_sequence(combined) == [1, 2, 3, 4]
    assert len(combined) == 12  # Block_2 (6) + Block_4 (6)
    assert info["combined_from_single_file"] is False
    assert [s["file"] for s in info["selected_files"]] == [
        "D9_Block_2_TrialData.mat",
        "D9_Block_4_TrialData.mat",
    ]


def test_select_single_cumulative_file(tmp_path):
    _save_trialdata(tmp_path / "D9_Block_2_TrialData.mat", [1, 1, 2, 2])
    _save_trialdata(tmp_path / "D9_Block_4_TrialData.mat", [1, 1, 2, 2, 3, 3, 4, 4])
    combined, info = select_and_combine(discover_trialdata_files(tmp_path))
    assert block_sequence(combined) == [1, 2, 3, 4]
    assert info["combined_from_single_file"] is True
    assert len(combined) == 8


def test_gap_raises(tmp_path):
    _save_trialdata(tmp_path / "D9_Block_1_TrialData.mat", [1])
    _save_trialdata(tmp_path / "D9_Block_3_TrialData.mat", [3])  # nothing ends at block 2
    with pytest.raises(IncompleteTrialInfoError, match="block 2"):
        select_and_combine(discover_trialdata_files(tmp_path))


def test_practice_excluded(tmp_path):
    _save_trialdata(tmp_path / "D9_Block_1_TrialData.mat", [1])
    _save_trialdata(tmp_path / "D9_Block_1_Practice_TrialData.mat", [1])
    files = discover_trialdata_files(tmp_path)
    assert [f.path.name for f in files] == ["D9_Block_1_TrialData.mat"]


def test_build_trialinfo_roundtrip(tmp_path):
    _save_trialdata(tmp_path / "D9_Block_2_TrialData.mat", [1, 1, 2, 2])
    _save_trialdata(tmp_path / "D9_Block_4_TrialData.mat", [3, 3, 4, 4])
    out = tmp_path / "trialInfo.mat"
    prov = tmp_path / "trialInfo.report.json"
    info = build_trialinfo(tmp_path, out, prov)

    assert out.exists() and prov.exists()
    assert info["total_trials"] == 8
    reloaded = load_trialinfo(out)
    assert len(reloaded) == 8
    assert block_sequence(reloaded) == [1, 2, 3, 4]


def test_discover_aggregates_multiple_dirs(tmp_path):
    # blocks split across two session folders (multi-session subject)
    s1, s2 = tmp_path / "sess1", tmp_path / "sess2"
    s1.mkdir()
    s2.mkdir()
    _save_trialdata(s1 / "D9_Block_2_TrialData.mat", [1, 1, 2, 2])
    _save_trialdata(s2 / "D9_Block_4_TrialData.mat", [3, 3, 4, 4])
    files = discover_trialdata_files([s1, s2])
    assert sorted(f.block_num for f in files) == [2, 4]
    combined, info = select_and_combine(files)
    assert block_sequence(combined) == [1, 2, 3, 4]
    assert len(combined) == 8
    assert info["multi_session"] is True
    assert info["n_session_dirs"] == 2


def test_select_cross_session_dup_prefers_most_complete(tmp_path):
    # block 3 appears in both sessions: half-aborted in sess1, full in sess2 -> take the full one
    s1, s2 = tmp_path / "sess1", tmp_path / "sess2"
    s1.mkdir()
    s2.mkdir()
    _save_trialdata(s1 / "D9_Block_2_TrialData.mat", [1, 1, 2, 2])
    _save_trialdata(s1 / "D9_Block_3_TrialData.mat", [1, 1, 2, 2, 3])  # aborted block 3 (1 trial)
    _save_trialdata(s2 / "D9_Block_3_TrialData.mat", [3, 3, 3])  # full block 3 redo
    _save_trialdata(s2 / "D9_Block_4_TrialData.mat", [3, 3, 3, 4, 4, 4])
    combined, info = select_and_combine(discover_trialdata_files([s1, s2]))
    assert block_sequence(combined) == [1, 2, 3, 4]
    # block 1+2 from sess1's Block_2 (4) + blocks 3+4 from sess2's Block_4 (6) = 10
    assert len(combined) == 10
    assert [s["file"] for s in info["selected_files"]] == [
        "D9_Block_2_TrialData.mat",
        "D9_Block_4_TrialData.mat",
    ]


def test_homogenize_trials():
    trials = [{"a": 1.0, "b": "x"}, {"a": 2.0}]
    out = homogenize_trials(trials)
    assert list(out[0].keys()) == ["a", "b"]  # sorted
    assert out[1]["b"] == ""  # char default
    trials2 = [{"a": 1.0}, {"b": 2.0}]
    out2 = homogenize_trials(trials2)
    assert math.isnan(out2[0]["b"])  # numeric default NaN


def test_fix_trialinfo_blocks_relabels_and_truncates():
    trials = [{"block": float(b)} for b in [1, 1, 2, 2, 3, 3]]
    fixed = fix_trialinfo_blocks(trials, [1, 2])
    assert [int(t["block"]) for t in fixed] == [1, 1, 2, 2]  # block-3 trials dropped


@pytest.mark.skipif(not _REAL.exists(), reason="CoganLab data not synced locally")
@pytest.mark.parametrize("subject", ["D140", "D134"])
def test_real_subject_combines_to_504(subject, tmp_path):
    ab = _REAL / subject / "Lexical No Delay" / "All Blocks"
    combined, info = select_and_combine(discover_trialdata_files(ab))
    assert block_sequence(combined) == [1, 2, 3, 4]
    assert len(combined) == 504
    assert info["combined_from_single_file"] is False
    # round-trip through save/load
    out = tmp_path / "trialInfo.mat"
    save_trialinfo(out, combined)
    assert len(load_trialinfo(out)) == 504
