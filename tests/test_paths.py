"""Tests for filesystem path builders."""

from __future__ import annotations

from pathlib import Path

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
