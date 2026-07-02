"""Phoneme Sequencing MFA config + the vendored nonword-syllable dictionary."""

from __future__ import annotations

import pytest

from rpcoding.core.mfa.runner import PIPELINE_DIR

_CONF = PIPELINE_DIR / "conf" / "task" / "phoneme_sequencing.yaml"
_DICT = PIPELINE_DIR / "dictionary" / "english_us_ps.dict"


def test_phoneme_sequencing_task_config():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load(_CONF.read_text(encoding="utf-8"))
    assert cfg["name"] == "phoneme_sequencing"
    assert cfg["mark_yes_no"] is False  # no Yes/No trials — every trial is a spoken repeat
    assert "stim_nested" not in cfg  # PS stim annotations are flat (unlike Uniqueness Point)
    assert cfg["mfa"]["dict"] == "english_us_ps"
    assert cfg["mfa"]["acoustic"] == "english_us_arpa"


def test_vendored_ps_dictionary_present_and_valid():
    assert _DICT.exists(), "english_us_ps.dict must be vendored"
    lines = [ln for ln in _DICT.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 65  # PS nonword syllable inventory
    for ln in lines:
        cols = ln.split("\t")
        assert len(cols) == 6  # token, 4 probability columns, phones (MFA v2 format)
        tok, phones = cols[0], cols[5]
        assert tok == tok.lower()  # keys match the lowercase stim labels
        syms = phones.split()
        assert syms
        for ph in syms:  # phone symbol, uppercase letters + optional trailing stress digit (AA1)
            base = ph.rstrip("012")
            assert base.isalpha() and base.isupper(), ph
