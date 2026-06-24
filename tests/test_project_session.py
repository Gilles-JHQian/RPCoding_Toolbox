"""Tests for the orchestration layer: scanner, step DAG, manifest, session state, runner, CLI."""

from __future__ import annotations

import time

import numpy as np
import scipy.io as sio
import soundfile as sf

from rpcoding.cli.main import main as cli_main
from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.manifest import Manifest
from rpcoding.core.runner import run_pipeline, run_step
from rpcoding.core.scanner import scan_subjects
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import STEP_SPECS, EffectiveState, Step
from rpcoding.core.tasks import Task

_TASK = Task.LEXICAL_NODELAY


def _save_trialdata(path, block_values):
    trials = [
        {"block": float(b), "cue": "Yes/No", "sound": f"s{i}.wav"}
        for i, b in enumerate(block_values)
    ]
    arr = np.empty((1, len(trials)), dtype=object)
    for i, t in enumerate(trials):
        arr[0, i] = t
    sio.savemat(str(path), {"trialInfo": arr})


def _build_subject(droot, subject="D9", fs=1000):
    """Create a minimal raw-acquisition tree (2 blocks) + D_Data folder for a subject."""
    cfg = AppConfig(droot=droot)
    ab = paths.cogan_task_data_dir(droot, subject, _TASK)
    ab.mkdir(parents=True)
    for b in (1, 2):
        sf.write(str(ab / f"{subject}_Block_{b}_AllTrials.wav"), np.zeros(fs), fs, subtype="PCM_16")
    _save_trialdata(ab / f"{subject}_Block_1_TrialData.mat", [1, 1])
    _save_trialdata(ab / f"{subject}_Block_2_TrialData.mat", [1, 1, 2, 2])
    paths.d_data_subject_dir(droot, _TASK, subject).mkdir(parents=True)
    return cfg


# ---- scanner ----


def test_scan_subjects(tmp_path):
    dd = paths.d_data_dir(tmp_path, _TASK)
    for name in ("D9", "S3", "D107B", "notes", "Practice"):
        (dd / name).mkdir(parents=True)
    assert scan_subjects(dd) == ["D9", "D107B", "S3"]


# ---- step DAG ----


def test_dag_is_topological():
    seen: set[Step] = set()
    for step, spec in STEP_SPECS.items():
        for dep in spec.deps:
            assert dep in STEP_SPECS
            assert dep in seen, f"{step} depends on {dep} which comes later"
        seen.add(step)


# ---- manifest ----


def test_manifest_roundtrip(tmp_path):
    m = Manifest("T", "D1")
    rec = m.record(Step.CONCAT_WAVS)
    rec.state = "done"
    rec.outputs = {"allblocks.wav": "123:456"}
    p = tmp_path / "m.json"
    m.save(p)
    m2 = Manifest.load(p)
    assert m2.steps[str(Step.CONCAT_WAVS)].state == "done"
    assert m2.steps[str(Step.CONCAT_WAVS)].outputs == {"allblocks.wav": "123:456"}


# ---- session state ----


def test_initial_states(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D1")
    st = s.effective_states()
    assert st[Step.CREATE_RESULTS] == EffectiveState.NOT_STARTED
    assert st[Step.CONCAT_WAVS] == EffectiveState.BLOCKED  # dep not done
    assert st[Step.MARK_FIRST_STIMS] == EffectiveState.BLOCKED


def test_state_progresses_with_done(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D1")
    s.record_done(Step.CREATE_RESULTS)
    assert s.effective_state(Step.CONCAT_WAVS) == EffectiveState.NOT_STARTED
    assert s.effective_state(Step.MARK_FIRST_STIMS) == EffectiveState.BLOCKED  # CONCAT not done


def test_staleness_when_first_stims_edited(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    rd = s.results_dir
    rd.mkdir(parents=True, exist_ok=True)
    for name in (
        paths.ALLBLOCKS_WAV,
        paths.BLOCK_WAV_ONSETS_MAT,
        paths.TRIALINFO_MAT,
        paths.CUE_EVENTS_TXT,
        paths.CONDITION_EVENTS_TXT,
    ):
        (rd / name).write_bytes(b"x")
    (rd / paths.FIRST_STIMS_TXT).write_text("1\t2\t1\n", newline="\n")
    for step in (
        Step.CREATE_RESULTS,
        Step.CONCAT_WAVS,
        Step.BUILD_TRIALINFO,
        Step.MARK_FIRST_STIMS,
        Step.MAKE_EVENTS,
    ):
        s.record_done(step)
    assert s.effective_state(Step.MAKE_EVENTS) == EffectiveState.DONE

    time.sleep(0.01)
    (rd / paths.FIRST_STIMS_TXT).write_text("9\t9\t1\n", newline="\n")  # edit upstream output
    assert s.effective_state(Step.MAKE_EVENTS) == EffectiveState.STALE


def _done_through_first_stims(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    rd = s.results_dir
    rd.mkdir(parents=True, exist_ok=True)
    for name in (paths.ALLBLOCKS_WAV, paths.BLOCK_WAV_ONSETS_MAT, paths.TRIALINFO_MAT):
        (rd / name).write_bytes(b"x")
    (rd / paths.FIRST_STIMS_TXT).write_text("1\t2\t1\n", newline="\n")
    for step in (
        Step.CREATE_RESULTS,
        Step.CONCAT_WAVS,
        Step.BUILD_TRIALINFO,
        Step.MARK_FIRST_STIMS,
    ):
        s.record_done(step)
    return s, rd


def test_mfa_denoise_does_not_stale_downstream(tmp_path):
    # MFA overwrites allblocks.wav in place (saving the original) — must NOT stale the chain.
    s, rd = _done_through_first_stims(tmp_path)
    assert s.effective_state(Step.MARK_FIRST_STIMS) == EffectiveState.DONE
    time.sleep(0.01)
    (rd / paths.ALLBLOCKS_WAV).write_bytes(b"denoised-and-a-different-size")
    (rd / paths.ALLBLOCKS_ORIGINAL_WAV).write_bytes(b"x")
    assert s.effective_state(Step.MARK_FIRST_STIMS) == EffectiveState.DONE


def test_reconcat_stales_downstream(tmp_path):
    # A genuine re-concat rewrites block_wav_onsets.mat — that SHOULD stale the chain.
    s, rd = _done_through_first_stims(tmp_path)
    time.sleep(0.01)
    (rd / paths.BLOCK_WAV_ONSETS_MAT).write_bytes(b"freshly-concatenated-onsets")
    assert s.effective_state(Step.MARK_FIRST_STIMS) == EffectiveState.STALE


def test_file_based_completion_without_manifest(tmp_path):
    """A subject processed by the legacy pipeline (outputs on disk, no manifest) shows green."""
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    rd = s.results_dir
    (rd / paths.MFA_DIRNAME).mkdir(parents=True)
    for name in (
        paths.ALLBLOCKS_WAV,
        paths.TRIALINFO_MAT,
        paths.FIRST_STIMS_TXT,
        paths.CUE_EVENTS_TXT,
        paths.CONDITION_EVENTS_TXT,
        paths.RESP_WORDS_ERRORS_TXT,
    ):
        (rd / name).write_bytes(b"x")
    (rd / paths.MFA_DIRNAME / "mfa_stim_words.txt").write_bytes(b"x")

    st = s.effective_states()
    for step in (
        Step.CREATE_RESULTS,
        Step.CONCAT_WAVS,
        Step.BUILD_TRIALINFO,
        Step.MARK_FIRST_STIMS,
        Step.MAKE_EVENTS,
        Step.RUN_MFA,
        Step.RESPONSE_CODING,
    ):
        assert st[step] == EffectiveState.DONE, step
    # write-Trials leaves no detectable artifact -> not auto-detected
    assert st[Step.WRITE_TRIALS] == EffectiveState.NOT_STARTED
    done, total, rep = s.summary()
    assert (done, total) == (7, 9) and rep == EffectiveState.NOT_STARTED


def test_disk_presence_overrides_error_record(tmp_path):
    """A leftover error record must not hide a step whose output is present (file = done)."""
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    s.results_dir.mkdir(parents=True)
    (s.results_dir / paths.ALLBLOCKS_WAV).write_bytes(b"x")
    s.record_error(Step.CONCAT_WAVS, "boom")
    assert s.effective_state(Step.CONCAT_WAVS) == EffectiveState.DONE


def test_error_shown_only_without_output(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    s.record_error(Step.CONCAT_WAVS, "boom")  # no allblocks.wav on disk
    assert s.effective_state(Step.CONCAT_WAVS) == EffectiveState.ERROR


def test_fingerprint_tolerates_oserror(tmp_path, monkeypatch):
    from pathlib import Path

    from rpcoding.core import manifest

    p = tmp_path / "x"
    p.write_bytes(b"x")

    def boom(self, *a, **k):  # simulate a Box cloud-sync placeholder (WinError 1006)
        raise OSError(1006, "volume changed")

    monkeypatch.setattr(Path, "stat", boom)
    assert manifest.fingerprint(p) is None


def test_summary_all_done_when_trials_recorded(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    rd = s.results_dir
    (rd / paths.MFA_DIRNAME).mkdir(parents=True)
    for name in (
        paths.ALLBLOCKS_WAV,
        paths.TRIALINFO_MAT,
        paths.FIRST_STIMS_TXT,
        paths.CUE_EVENTS_TXT,
        paths.CONDITION_EVENTS_TXT,
        paths.RESP_WORDS_ERRORS_TXT,
    ):
        (rd / name).write_bytes(b"x")
    (rd / paths.MFA_DIRNAME / "mfa_stim_words.txt").write_bytes(b"x")
    s.record_done(Step.DENOISE)
    s.record_done(Step.WRITE_TRIALS)
    done, total, rep = s.summary()
    assert (done, total) == (9, 9) and rep == EffectiveState.DONE


# ---- runner ----


def test_run_steps_concat_and_trialinfo(tmp_path):
    cfg = _build_subject(tmp_path)
    s = SubjectSession(cfg, _TASK, "D9")
    run_step(s, Step.CREATE_RESULTS)
    run_step(s, Step.CONCAT_WAVS)
    run_step(s, Step.BUILD_TRIALINFO)
    assert s.output_path(paths.ALLBLOCKS_WAV).exists()
    assert s.output_path(paths.TRIALINFO_MAT).exists()
    assert s.effective_state(Step.CONCAT_WAVS) == EffectiveState.DONE
    assert s.effective_state(Step.BUILD_TRIALINFO) == EffectiveState.DONE


def test_run_pipeline_stops_at_manual(tmp_path):
    cfg = _build_subject(tmp_path)
    s = SubjectSession(cfg, _TASK, "D9")
    ran = run_pipeline(s)
    assert ran == [Step.CREATE_RESULTS, Step.CONCAT_WAVS, Step.BUILD_TRIALINFO]
    # MAKE_EVENTS is blocked on the manual first-stims step
    assert s.effective_state(Step.MAKE_EVENTS) == EffectiveState.BLOCKED


def test_run_step_records_error(tmp_path):
    # no raw data -> concat fails; error recorded and re-raised
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    run_step(s, Step.CREATE_RESULTS)
    import pytest

    with pytest.raises((FileNotFoundError, ValueError)):
        run_step(s, Step.CONCAT_WAVS)
    assert s.effective_state(Step.CONCAT_WAVS) == EffectiveState.ERROR


# ---- CLI ----


def test_cli_scan(tmp_path, capsys):
    dd = paths.d_data_dir(tmp_path, _TASK)
    for name in ("D9", "S3"):
        (dd / name).mkdir(parents=True)
    rc = cli_main(["scan", "--droot", str(tmp_path), "--task", "LexicalDecRepNoDelay"])
    out = capsys.readouterr().out.split()
    assert rc == 0
    assert out == ["D9", "S3"]
