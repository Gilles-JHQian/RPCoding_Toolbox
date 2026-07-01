"""Tests for merging multi-part recording files (Trials/trialInfo concat + experiment copy)."""

from __future__ import annotations

import numpy as np
import scipy.io as sio

from rpcoding.core.multipart import merge_subject, numbered_parts


def _save_struct(path, var, n, base_val=0):
    """A 1xN MATLAB struct array with Trial/Auditory fields (stands in for Trials/trialInfo)."""
    arr = np.zeros((1, n), dtype=[("Trial", "O"), ("Auditory", "O")])
    for i in range(n):
        arr[0, i]["Trial"] = i + 1
        arr[0, i]["Auditory"] = base_val + i
    sio.savemat(str(path), {var: arr})


def _make_subject(root, n1, n2):
    subj = root / "D9"
    dm = subj / "230101" / "mat"
    dm.mkdir(parents=True)
    (subj / "mat").mkdir(parents=True)
    _save_struct(dm / "Trials1.mat", "Trials", n1)
    _save_struct(dm / "Trials2.mat", "Trials", n2, base_val=1000)
    _save_struct(dm / "trialInfo1.mat", "trialInfo", n1)
    _save_struct(dm / "trialInfo2.mat", "trialInfo", n2)
    sio.savemat(str(subj / "mat" / "experiment1.mat"), {"experiment": np.array([[1.0]])})
    sio.savemat(str(subj / "mat" / "experiment2.mat"), {"experiment": np.array([[1.0]])})
    return subj


def test_numbered_parts_matches_only_numeric_siblings(tmp_path):
    for name in ("Trials1.mat", "Trials2.mat", "Trials.mat", "Trials_org.mat", "trialInfo1.mat"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in numbered_parts(tmp_path, "Trials")] == ["Trials1.mat", "Trials2.mat"]
    assert [p.name for p in numbered_parts(tmp_path, "trialInfo")] == ["trialInfo1.mat"]


def test_merge_subject_concats_and_copies(tmp_path):
    subj = _make_subject(tmp_path, 5, 7)
    results = {r.name: r for r in merge_subject(subj)}
    assert results["Trials.mat"].status == "merged"
    assert results["trialInfo.mat"].status == "merged"
    assert results["experiment.mat"].status == "merged"
    # Trials / trialInfo concatenated to n1 + n2
    assert sio.loadmat(str(subj / "230101" / "mat" / "Trials.mat"))["Trials"].shape[1] == 12
    assert sio.loadmat(str(subj / "230101" / "mat" / "trialInfo.mat"))["trialInfo"].shape[1] == 12
    # experiment copied byte-for-byte from part 1 (parts are content-identical)
    assert (subj / "mat" / "experiment.mat").read_bytes() == (
        subj / "mat" / "experiment1.mat"
    ).read_bytes()


def test_merge_is_idempotent(tmp_path):
    subj = _make_subject(tmp_path, 3, 4)
    merge_subject(subj)
    again = {r.name: r.status for r in merge_subject(subj)}
    assert again == {"Trials.mat": "exists", "trialInfo.mat": "exists", "experiment.mat": "exists"}


def test_single_part_is_not_merged(tmp_path):
    subj = tmp_path / "D9"
    dm = subj / "230101" / "mat"
    dm.mkdir(parents=True)
    (subj / "mat").mkdir(parents=True)
    _save_struct(dm / "Trials1.mat", "Trials", 5)
    _save_struct(dm / "trialInfo1.mat", "trialInfo", 5)
    sio.savemat(str(subj / "mat" / "experiment1.mat"), {"experiment": np.array([[1.0]])})
    statuses = {r.name: r.status for r in merge_subject(subj)}
    assert set(statuses.values()) == {"single_part"}
    assert not (dm / "Trials.mat").exists()  # nothing written


def test_no_parts_is_safe(tmp_path):
    subj = tmp_path / "D9"
    (subj / "mat").mkdir(parents=True)
    assert all(r.status == "no_parts" for r in merge_subject(subj))
