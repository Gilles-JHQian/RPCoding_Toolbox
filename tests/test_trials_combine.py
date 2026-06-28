"""Tests for multi-session Trials.mat resolution / auto-combine (trials_combine.py)."""

from __future__ import annotations

import pytest

from rpcoding.core.matio import load_trials
from rpcoding.core.rpcode.rpcode2trials import save_trials
from rpcoding.core.trials_combine import (
    ResolvedTrials,
    combine_session_trials,
    resolve_trials_mat,
)


def _trials(n: int, start_auditory: float = 1000.0) -> list[dict]:
    """A minimal Trials list (each per-session file restarts Trial numbering at 1, like MATLAB)."""
    return [
        {"Trial": i + 1, "Auditory": start_auditory + i, "Start": start_auditory + i - 50}
        for i in range(n)
    ]


def _save(path, trials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_trials(path, trials)


# ---- combine_session_trials ----


def test_combine_renumbers_trial_continuously():
    combined = combine_session_trials([_trials(2, 10), _trials(3, 100)])
    assert len(combined) == 5
    assert [int(t["Trial"]) for t in combined] == [1, 2, 3, 4, 5]
    # everything else is plain concatenation, in session order
    assert [t["Auditory"] for t in combined] == [10, 11, 100, 101, 102]


def test_combine_preserves_trial_field_type():
    combined = combine_session_trials([[{"Trial": 1.0, "Auditory": 5.0}]])
    assert isinstance(combined[0]["Trial"], float)  # MATLAB double stays double


# ---- resolve_trials_mat ----


def test_resolve_uses_existing_combined(tmp_path):
    dd = tmp_path / "D9"
    _save(dd / "230101" / "mat" / "Trials.mat", _trials(4))
    res = resolve_trials_mat(dd, tmp_path / "results")
    assert isinstance(res, ResolvedTrials)
    assert res.auto_combined is False
    assert res.path == dd / "230101" / "mat" / "Trials.mat"


def test_resolve_auto_combines_two_sessions(tmp_path):
    dd = tmp_path / "D9"
    _save(dd / "230101" / "mat" / "Trials1.mat", _trials(2, 10))
    _save(dd / "230102" / "mat" / "Trials2.mat", _trials(3, 100))
    results = tmp_path / "results"
    res = resolve_trials_mat(dd, results)
    assert res.auto_combined is True
    assert res.multi_session is True
    assert res.n_trials == 5
    assert res.path == results / "Trials.mat"
    reloaded = load_trials(res.path)
    assert [int(t["Trial"]) for t in reloaded] == [1, 2, 3, 4, 5]  # renumbered across sessions


def test_resolve_prefers_existing_combined_over_sessions(tmp_path):
    """If a hand-made combined Trials.mat exists, use it even when per-session files are present."""
    dd = tmp_path / "D9"
    _save(dd / "230101" / "mat" / "Trials1.mat", _trials(2, 10))
    _save(dd / "230102" / "mat" / "Trials2.mat", _trials(3, 100))
    combined = combine_session_trials([_trials(2, 10), _trials(3, 100)])
    _save(dd / "230102" / "mat" / "Trials.mat", combined)
    res = resolve_trials_mat(dd, tmp_path / "results")
    assert res.auto_combined is False
    assert res.multi_session is True  # the per-session files are still detected
    assert res.path == dd / "230102" / "mat" / "Trials.mat"


def test_resolve_lone_suffixed_session(tmp_path):
    dd = tmp_path / "D9"
    _save(dd / "230101" / "mat" / "Trials1.mat", _trials(4))
    res = resolve_trials_mat(dd, tmp_path / "results")
    assert res.auto_combined is False
    assert res.multi_session is False
    assert res.path == dd / "230101" / "mat" / "Trials1.mat"


def test_resolve_none_raises(tmp_path):
    dd = tmp_path / "D9"
    (dd / "230101" / "mat").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        resolve_trials_mat(dd, tmp_path / "results")


def test_resolve_two_combined_dates_is_ambiguous(tmp_path):
    dd = tmp_path / "D9"
    _save(dd / "230101" / "mat" / "Trials.mat", _trials(4))
    _save(dd / "230102" / "mat" / "Trials.mat", _trials(4))
    with pytest.raises(ValueError, match="More than one combined"):
        resolve_trials_mat(dd, tmp_path / "results")


def test_resolve_prefers_canonical_over_stray(tmp_path):
    dd = tmp_path / "D9"
    canonical = dd / "230101" / "mat" / "Trials.mat"
    _save(canonical, _trials(4))
    _save(dd / "mat" / "Trials.mat", _trials(4))  # stray non-canonical copy
    res = resolve_trials_mat(dd, tmp_path / "results")
    assert res.path == canonical
