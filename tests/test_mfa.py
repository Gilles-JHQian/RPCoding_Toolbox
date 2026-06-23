"""Tests for MFA integration: ingest, command building, input checks, stub run, dict install."""

from __future__ import annotations

import textwrap

import pytest

from rpcoding.core.mfa.ingest import ingest_mfa_tiers
from rpcoding.core.mfa.models import install_custom_dicts
from rpcoding.core.mfa.runner import build_mfa_command, run_mfa, verify_inputs


def test_ingest_mfa_tiers(tmp_path):
    mfa = tmp_path / "mfa"
    mfa.mkdir()
    (mfa / "mfa_stim_words.txt").write_text("0.000000\t1.000000\tfolip\n", newline="\n")
    (mfa / "mfa_resp_words.txt").write_text("1.0\t2.0\tyes\n", newline="\n")
    tiers = ingest_mfa_tiers(mfa)
    assert set(tiers) == {"mfa_stim_words", "mfa_resp_words"}
    assert tiers["mfa_stim_words"].intervals[0].label == "folip"


def test_build_mfa_command():
    cmd, cwd = build_mfa_command(
        "/data/results", "lexical_repeat_no_delay", "D9", python_exe="py", home_dir="/home"
    )
    assert cmd[0] == "py"
    assert cmd[1].endswith("mfa_pipeline.py")
    assert "patient_dir=/data/results" in cmd
    assert "task=lexical_repeat_no_delay" in cmd
    assert "patients=D9" in cmd
    assert "home_dir=/home" in cmd
    assert cwd.name == "pipeline"


def test_verify_inputs(tmp_path):
    (tmp_path / "D9").mkdir()
    assert len(verify_inputs(tmp_path, "D9")) == 3  # all required inputs missing
    for req in ("allblocks.wav", "cue_events.txt", "trialInfo.mat"):
        (tmp_path / "D9" / req).write_bytes(b"x")
    assert verify_inputs(tmp_path, "D9") == []


def test_run_mfa_missing_inputs_raises(tmp_path):
    (tmp_path / "D9").mkdir()
    with pytest.raises(FileNotFoundError):
        run_mfa(tmp_path, "lexical_repeat", "D9", pipeline_dir=tmp_path)


def test_run_mfa_with_stub_pipeline(tmp_path):
    # a stand-in mfa_pipeline.py that parses key=value args and writes a dummy output tier
    pdir = tmp_path / "pipeline"
    pdir.mkdir()
    (pdir / "mfa_pipeline.py").write_text(
        textwrap.dedent("""
            import os, sys
            kv = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
            out = os.path.join(kv["patient_dir"], kv["patients"], "mfa")
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "mfa_stim_words.txt"), "w") as f:
                f.write("0.0\\t1.0\\tx\\n")
            print("STUB", kv["task"])
            """),
        newline="\n",
    )
    patient_dir = tmp_path / "results"
    (patient_dir / "D9").mkdir(parents=True)

    res = run_mfa(
        patient_dir, "lexical_repeat_no_delay", "D9", pipeline_dir=pdir, check_inputs=False
    )
    assert res.returncode == 0
    assert "STUB lexical_repeat_no_delay" in res.log
    assert (patient_dir / "D9" / "mfa" / "mfa_stim_words.txt").exists()


def test_install_custom_dicts(tmp_path):
    copied = install_custom_dicts(tmp_path)
    names = sorted(p.name for p in copied)
    assert "english_us_lr.dict" in names
    assert all((tmp_path / n).exists() for n in names)
