"""Tests for AppConfig defaults and JSON round-trip."""

from __future__ import annotations

from pathlib import Path

from rpcoding.core.config import AppConfig
from rpcoding.core.tasks import Task


def test_defaults_filled():
    cfg = AppConfig(droot=Path("/data/CoganLab"))
    assert cfg.mfa_task(Task.LEXICAL_DELAY) == "lexical_repeat"
    assert cfg.mfa_task(Task.LEXICAL_NODELAY) == "lexical_repeat_no_delay"
    assert cfg.mfa_task(Task.UNIQUENESS_POINT) is None


def test_override_and_roundtrip(tmp_path):
    cfg = AppConfig(
        droot=tmp_path / "CoganLab",
        mfa_task_map={"Uniqueness_Point": "uniqueness_point"},
    )
    p = tmp_path / "cfg.json"
    cfg.save(p)
    loaded = AppConfig.load(p)

    assert loaded.droot == cfg.droot
    # explicit override preserved, defaults still present
    assert loaded.mfa_task("Uniqueness_Point") == "uniqueness_point"
    assert loaded.mfa_task(Task.LEXICAL_DELAY) == "lexical_repeat"
