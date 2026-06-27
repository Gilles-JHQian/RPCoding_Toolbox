"""Tests for filesystem path builders."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpcoding.core import paths
from rpcoding.core.tasks import Task


def test_d_data_subject_dir():
    droot = Path("/box/CoganLab")
    assert paths.d_data_subject_dir(droot, Task.LEXICAL_DELAY, "D140") == (
        droot / "D_Data" / "LexicalDecRepDelay" / "D140"
    )


def test_results_dir_accepts_str_task():
    droot = Path("/box/CoganLab")
    assert paths.results_dir(droot, "Uniqueness_Point", "D77") == (
        droot
        / "ECoG_Task_Data"
        / "response_coding"
        / "response_coding_results"
        / "Uniqueness_Point"
        / "D77"
    )


def test_cogan_task_data_dir_uses_human_folder_name():
    droot = Path("/box/CoganLab")
    d = paths.cogan_task_data_dir(droot, "D140", Task.LEXICAL_NODELAY)
    assert d.name == "All Blocks"
    assert d.parent.name == "Lexical No Delay"  # not the task id
    assert d.parent.parent.name == "D140"


def _make_block_mats(directory: Path, subject: str, *blocks: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for b in blocks:
        (directory / f"{subject}_Block_{b}_TrialData.mat").write_bytes(b"x")


def test_resolve_blocks_dir_conventional(tmp_path):
    subj = tmp_path / "D9"
    blocks = subj / "Lexical No Delay" / "All Blocks"
    _make_block_mats(blocks, "D9", 1, 2)
    assert paths.resolve_blocks_dir(subj, Task.LEXICAL_NODELAY) == blocks


def test_resolve_blocks_dir_messy_session_folder(tmp_path):
    subj = tmp_path / "D24"  # task folder 'Lexical', a nested timestamped session, + competitors
    real = subj / "Lexical" / "Within_2x" / "D24_Lex_DecisionRepeat_NoDelay_201810281549"
    _make_block_mats(real, "D24", 1, 2, 3, 4)
    (real / "D24_Block_1_Pract_TrialData.mat").write_bytes(b"x")  # practice must be ignored
    _make_block_mats(subj / "Lexical" / "Within_2x" / "D24_WithinBlock_2018", "D24", 1)
    assert paths.resolve_blocks_dir(subj, Task.LEXICAL_NODELAY) == real


def test_resolve_blocks_dir_delay_vs_nodelay(tmp_path):
    subj = tmp_path / "D50"
    nod = subj / "Lexical" / "D50_Lex_NoDelay_x"
    dly = subj / "Lexical" / "D50_Lex_Delay_y"
    _make_block_mats(nod, "D50", 1)
    _make_block_mats(dly, "D50", 1)
    assert paths.resolve_blocks_dir(subj, Task.LEXICAL_NODELAY) == nod
    assert paths.resolve_blocks_dir(subj, Task.LEXICAL_DELAY) == dly


def test_resolve_blocks_dir_fallback_when_absent(tmp_path):
    subj = tmp_path / "D1"
    subj.mkdir()
    assert paths.resolve_blocks_dir(subj, Task.LEXICAL_NODELAY) == (
        subj / "Lexical No Delay" / "All Blocks"
    )


# ---- find_trials_mat ----


def _make_trials(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def test_find_trials_mat_single(tmp_path):
    subj = tmp_path / "D94"
    want = _make_trials(subj / "230809" / "mat" / "Trials.mat")
    assert paths.find_trials_mat(subj) == want


def test_find_trials_mat_none_raises(tmp_path):
    subj = tmp_path / "D94"
    subj.mkdir()
    with pytest.raises(FileNotFoundError):
        paths.find_trials_mat(subj)


def test_find_trials_mat_prefers_canonical_date_folder(tmp_path):
    """D94 has both <date>/mat/Trials.mat (canonical) and a stray <subject>/mat/Trials.mat;
    prefer the canonical date-folder copy instead of erroring."""
    subj = tmp_path / "D94"
    canonical = _make_trials(subj / "230809" / "mat" / "Trials.mat")
    _make_trials(subj / "mat" / "Trials.mat")  # stray non-canonical duplicate
    assert paths.find_trials_mat(subj) == canonical


def test_find_trials_mat_single_noncanonical_still_resolves(tmp_path):
    """A lone copy that isn't under a date folder is still usable (no ambiguity)."""
    subj = tmp_path / "D94"
    want = _make_trials(subj / "mat" / "Trials.mat")
    assert paths.find_trials_mat(subj) == want


def test_find_trials_mat_two_date_folders_is_ambiguous(tmp_path):
    """Two canonical copies (two recording dates) are genuinely ambiguous -> raise."""
    subj = tmp_path / "D94"
    _make_trials(subj / "230809" / "mat" / "Trials.mat")
    _make_trials(subj / "230810" / "mat" / "Trials.mat")
    with pytest.raises(ValueError, match="more than one Trials.mat"):
        paths.find_trials_mat(subj)
