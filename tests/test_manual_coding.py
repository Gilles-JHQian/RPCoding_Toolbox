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


# Both manual steps share one unified lane layout (first stim, condition, cue, response).
_UNIFIED = ["first_stims", "condition_events", "cue_events", "response"]


def test_tiers_for_step_first_stims(tmp_path):
    specs, save_path = tiers_for_step(tmp_path, Step.MARK_FIRST_STIMS)
    assert save_path == tmp_path / "first_stims.txt"
    assert [name for name, _t, _e in specs] == _UNIFIED
    # only first_stims is editable on this step
    assert [name for name, _t, e in specs if e] == ["first_stims"]


def test_tiers_for_step_response_coding(tmp_path):
    write_tier(Tier("cue", [Interval(1, 2, "1_casef.wav")]), tmp_path / "cue_events.txt")
    write_tier(Tier("cond", [Interval(1, 1.5, "1_Yes/No")]), tmp_path / "condition_events.txt")
    write_tier(Tier("r", [Interval(3, 4, "1_no")]), tmp_path / "bsliang_resp_words_errors.txt")

    specs, save_path = tiers_for_step(tmp_path, Step.RESPONSE_CODING)
    assert save_path == tmp_path / "bsliang_resp_words_errors.txt"
    assert [name for name, _t, _e in specs] == _UNIFIED
    # only the response tier is editable, and it loaded the saved coding
    assert [name for name, _t, e in specs if e] == ["response"]
    assert specs[-1][1].intervals[0].label == "1_no"


def test_response_tier_falls_back_to_mfa(tmp_path):
    # no saved coding yet -> the response lane starts from the MFA-aligned response words
    write_tier(Tier("r", [Interval(3, 4, "no")]), tmp_path / "mfa" / "mfa_resp_words.txt")
    specs, _save = tiers_for_step(tmp_path, Step.RESPONSE_CODING)
    resp = next(t for name, t, _e in specs if name == "response")
    assert [iv.label for iv in resp.intervals] == ["no"]


def test_tiers_for_step_rejects_auto_step(tmp_path):
    with pytest.raises(ValueError, match="not an editor-backed manual step"):
        tiers_for_step(tmp_path, Step.CONCAT_WAVS)


def test_write_trials_requires_word_lists(tmp_path):
    cfg = AppConfig(droot=tmp_path)  # no word_list / nonword_list
    session = SubjectSession(cfg, Task.LEXICAL_NODELAY, "D999")
    with pytest.raises(ValueError, match="Word/nonword lists are not configured"):
        _write_trials(session)
