"""Manual-coding integration (pure): config word lists, step->tiers, write-Trials guard."""

from __future__ import annotations

import pytest

from rpcoding.core.config import AppConfig
from rpcoding.core.labels import Interval, Tier, write_tier
from rpcoding.core.runner import _write_trials
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import Step
from rpcoding.core.tasks import Task
from rpcoding.gui.editor_loader import tiers_for_step


def test_config_word_lists_roundtrip(tmp_path):
    cfg = AppConfig(
        droot=tmp_path / "CoganLab",
        word_list=tmp_path / "word_lst.mat",
        nonword_list=tmp_path / "nonword_lst.mat",
    )
    path = tmp_path / "config.json"
    cfg.save(path)
    loaded = AppConfig.load(path)
    assert loaded.word_list == tmp_path / "word_lst.mat"
    assert loaded.nonword_list == tmp_path / "nonword_lst.mat"


def test_config_word_lists_default_none(tmp_path):
    cfg = AppConfig(droot=tmp_path)
    assert cfg.word_list is None and cfg.nonword_list is None
    d = cfg.to_dict()
    assert d["word_list"] is None and d["nonword_list"] is None
    # round-trips back to None (not the string "None")
    assert AppConfig.from_dict(d).word_list is None


def test_tiers_for_step_first_stims(tmp_path):
    specs, save_path = tiers_for_step(tmp_path, Step.MARK_FIRST_STIMS)
    assert save_path == tmp_path / "first_stims.txt"
    assert [(name, editable) for name, _t, editable in specs] == [("first_stims", True)]
    # missing file -> empty editable tier
    assert specs[0][1].intervals == []


def test_tiers_for_step_response_coding(tmp_path):
    write_tier(Tier("cue", [Interval(1, 2, "1_casef.wav")]), tmp_path / "cue_events.txt")
    write_tier(Tier("cond", [Interval(1, 1.5, "1_Yes/No")]), tmp_path / "condition_events.txt")
    write_tier(Tier("s", [Interval(1, 2, "casef")]), tmp_path / "mfa" / "mfa_stim_words.txt")
    write_tier(Tier("r", [Interval(3, 4, "1_no")]), tmp_path / "bsliang_resp_words_errors.txt")

    specs, save_path = tiers_for_step(tmp_path, Step.RESPONSE_CODING)
    assert save_path == tmp_path / "bsliang_resp_words_errors.txt"
    names = [name for name, _t, _e in specs]
    assert names[:2] == ["cue_events", "condition_events"]
    assert "mfa_stim_words" in names
    # exactly one editable tier, the response tier, and it comes last
    editable = [name for name, _t, e in specs if e]
    assert editable == ["response"] and names[-1] == "response"
    resp_tier = specs[-1][1]
    assert resp_tier.intervals[0].label == "1_no"  # pre-existing content loaded back


def test_tiers_for_step_rejects_auto_step(tmp_path):
    with pytest.raises(ValueError, match="not an editor-backed manual step"):
        tiers_for_step(tmp_path, Step.CONCAT_WAVS)


def test_write_trials_requires_word_lists(tmp_path):
    cfg = AppConfig(droot=tmp_path)  # no word_list / nonword_list
    session = SubjectSession(cfg, Task.LEXICAL_NODELAY, "D999")
    with pytest.raises(ValueError, match="Word/nonword lists are not configured"):
        _write_trials(session)
