"""Uniqueness Point MFA adaptation: dictionary builder, task config, and the nested stim loader."""

from __future__ import annotations

import importlib.util
import sys

import pytest

from rpcoding.core.mfa import up_dict
from rpcoding.core.mfa.runner import PIPELINE_DIR
from rpcoding.core.mfa.up_dict import DEFAULT_OUT

_CONF = PIPELINE_DIR / "conf" / "task" / "uniqueness_point.yaml"


# ---- dictionary builder ----
def test_parse_phones_with_word_level_line(tmp_path):
    # Some _phones.txt carry a leading lowercase word-level row; it must be ignored.
    f = tmp_path / "aartahstrah_phones.txt"
    f.write_text("0.0\t0.78\taartahstrah\n0.0\t0.06\tAA1\n0.06\t0.21\tR\n", encoding="utf-8")
    assert up_dict.parse_phones(f) == ["AA1", "R"]


def test_parse_phones_without_word_level_line(tmp_path):
    # …others start straight at the phones (the format is inconsistent across tokens).
    f = tmp_path / "algebra_phones.txt"
    f.write_text("0.0\t0.15\tAE1\n0.15\t0.28\tL\n0.28\t0.4\tJH\n", encoding="utf-8")
    assert up_dict.parse_phones(f) == ["AE1", "L", "JH"]


def test_parse_phones_skips_silence_markers(tmp_path):
    f = tmp_path / "x_phones.txt"
    f.write_text("0\t1\tx\n0\t0.1\tsil\n0.1\t0.2\tK\n0.2\t0.3\tsp\n", encoding="utf-8")
    assert up_dict.parse_phones(f) == ["K"]


def test_build_up_dictionary_nested_and_format(tmp_path):
    layout = {
        "aartahstrah": "0\t0.7\taartahstrah\n0\t0.1\tAA1\n0.1\t0.2\tR\n",
        "algebra": "0\t0.1\tAE1\n0.1\t0.2\tL\n",
    }
    for tok, rows in layout.items():
        d = tmp_path / tok
        d.mkdir()
        (d / f"{tok}_phones.txt").write_text(rows, encoding="utf-8")
    entries = up_dict.build_up_dictionary(tmp_path)
    assert entries == {"aartahstrah": ["AA1", "R"], "algebra": ["AE1", "L"]}
    # MFA dict text: sorted, one `token<TAB>PH PH` line per token.
    assert up_dict.format_dictionary(entries) == "aartahstrah\tAA1 R\nalgebra\tAE1 L\n"


def test_build_up_dictionary_skips_tokens_without_phones(tmp_path):
    d = tmp_path / "blank"
    d.mkdir()
    (d / "blank_phones.txt").write_text("0\t1\tblank\n", encoding="utf-8")  # word row only
    assert up_dict.build_up_dictionary(tmp_path) == {}


# ---- the vendored dictionary that ships with the tool ----
def test_vendored_up_dictionary_present_and_valid():
    assert DEFAULT_OUT.exists(), "english_us_up.dict must be vendored"
    lines = [ln for ln in DEFAULT_OUT.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 80  # UP = 40 words + 40 nonwords
    for ln in lines:
        tok, tab, phones = ln.partition("\t")
        assert tab and tok and phones  # token<TAB>phones
        assert tok == tok.lower()  # keys match the lowercase stim labels


# ---- task config ----
def test_uniqueness_point_task_config():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load(_CONF.read_text(encoding="utf-8"))
    assert cfg["name"] == "uniqueness_point"
    assert cfg["stim_nested"] is True  # the removable nested-layout branch
    assert cfg["mark_yes_no"] is False  # Yes/No is a button press in UP
    assert cfg["mfa"]["dict"] == "english_us_up"
    assert cfg["mfa"]["acoustic"] == "english_us_arpa"


# ---- the vendored loader's UP-only nested branch ----
def _load_mfa_utils():
    pytest.importorskip("textgrid")
    pytest.importorskip("noisereduce")
    utils_dir = PIPELINE_DIR / "utils"
    sys.path.insert(0, str(utils_dir))
    spec = importlib.util.spec_from_file_location("mfa_utils", utils_dir / "mfa_utils.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_annots_nested_only_when_requested(tmp_path):
    mfa_utils = _load_mfa_utils()
    (tmp_path / "flat_words.txt").write_text("0\t1\tflat\n", encoding="utf-8")
    sub = tmp_path / "tok"
    sub.mkdir()
    (sub / "tok_words.txt").write_text("0\t1\ttok\n", encoding="utf-8")

    flat = mfa_utils.loadAnnotsToDict(tmp_path, tier_name="words")
    assert set(flat["words"]) == {"flat"}  # default: subfolder files are not found

    nested = mfa_utils.loadAnnotsToDict(tmp_path, tier_name="words", nested=True)
    assert set(nested["words"]) == {"flat", "tok"}  # nested: one level deeper too
