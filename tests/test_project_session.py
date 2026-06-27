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


def test_manifest_notes_and_flag_roundtrip(tmp_path):
    m = Manifest("T", "D1")
    m.notes = "block 3 noisy"
    m.flagged = True
    p = tmp_path / "m.json"
    m.save(p)
    m2 = Manifest.load(p)
    assert m2.notes == "block 3 noisy"
    assert m2.flagged is True
    # back-compat: a manifest written before these fields existed loads with defaults
    legacy = Manifest.from_dict({"task": "T", "subject": "D1"})
    assert legacy.notes == "" and legacy.flagged is False


def test_session_notes_and_flag_persist(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    assert s.notes == "" and s.flagged is False
    s.set_notes("redo response coding")
    s.set_flagged(True)
    s2 = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")  # reloads from the saved manifest
    assert s2.notes == "redo response coding"
    assert s2.flagged is True


def test_flagged_subject_summary_is_flagged(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    assert s.summary()[2] == EffectiveState.NOT_STARTED
    s.set_flagged(True)
    assert s.summary()[2] == EffectiveState.FLAGGED  # the manual flag wins over computed status


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
    # 8 required steps (the optional Denoise is excluded); 7 done, write-Trials still missing.
    assert (done, total) == (7, 8) and rep == EffectiveState.NOT_STARTED


def test_empty_mfa_output_is_not_done(tmp_path):
    """A 0-byte mfa_stim_words.txt is a failed/aborted MFA run — it must not show as DONE."""
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    rd = s.results_dir
    (rd / paths.MFA_DIRNAME).mkdir(parents=True)
    for name in (paths.CUE_EVENTS_TXT, paths.CONDITION_EVENTS_TXT):
        (rd / name).write_bytes(b"x")
    (rd / paths.MFA_DIRNAME / "mfa_stim_words.txt").write_bytes(b"")  # empty == not produced
    assert s.effective_state(Step.RUN_MFA) != EffectiveState.DONE


def test_error_record_wins_over_present_output(tmp_path):
    """A recorded error from our last run shows ERROR even if a (stale/pre-existing) output is still
    on disk — e.g. a step-6 re-run that fails while the prior run's events file lingers, or
    write-Trials, whose output doubles as its input and therefore always 'exists'."""
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    s.results_dir.mkdir(parents=True)
    (s.results_dir / paths.ALLBLOCKS_WAV).write_bytes(b"x")
    s.record_error(Step.CONCAT_WAVS, "boom")
    assert s.effective_state(Step.CONCAT_WAVS) == EffectiveState.ERROR


def test_error_cleared_by_subsequent_done(tmp_path):
    """Re-running the step successfully clears the error (record_done wins)."""
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    s.results_dir.mkdir(parents=True)
    (s.results_dir / paths.ALLBLOCKS_WAV).write_bytes(b"x")
    s.record_error(Step.CONCAT_WAVS, "boom")
    s.record_done(Step.CONCAT_WAVS)
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
    # 8 required steps all done (the optional Denoise is excluded from the count) -> green.
    assert (done, total) == (8, 8) and rep == EffectiveState.DONE


def test_optional_denoise_not_done_still_green(tmp_path):
    # Everything required is done but the optional Denoise step never ran -> still complete (green).
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
    s.record_done(Step.WRITE_TRIALS)  # the one required step with no on-disk artifact
    assert s.effective_state(Step.DENOISE) == EffectiveState.NOT_STARTED  # optional, never ran
    assert s.summary() == (8, 8, EffectiveState.DONE)
    assert s.status()[3] is None  # all required done -> no current step


def test_status_current_step(tmp_path):
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    assert s.status()[3] == Step.CREATE_RESULTS  # nothing done -> at the first step
    s.results_dir.mkdir(parents=True)
    (s.results_dir / paths.ALLBLOCKS_WAV).write_bytes(b"x")  # create + concat now done on disk
    # the next required step (the optional Denoise is skipped in the frontier)
    assert s.status()[3] == Step.BUILD_TRIALINFO


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


def test_run_step_reports_progress(tmp_path):
    cfg = _build_subject(tmp_path)
    s = SubjectSession(cfg, _TASK, "D9")
    ticks: list = []
    run_step(s, Step.CREATE_RESULTS, report=lambda f, m: ticks.append((f, m)))
    assert ticks and ticks[-1][0] == 1.0  # ends at 100%
    assert all(isinstance(m, str) and m for _f, m in ticks)


def test_run_pipeline_reports_step_progress(tmp_path):
    cfg = _build_subject(tmp_path)
    s = SubjectSession(cfg, _TASK, "D9")
    events: list = []
    ran = run_pipeline(s, on_step=events.append)
    assert ran == [Step.CREATE_RESULTS, Step.CONCAT_WAVS, Step.BUILD_TRIALINFO]
    # Every event knows the pass has 3 runnable steps; steps appear in order with 1-based indices.
    assert {e.total for e in events} == {3}
    first_seen = list(dict.fromkeys(e.step for e in events))
    assert first_seen == [Step.CREATE_RESULTS, Step.CONCAT_WAVS, Step.BUILD_TRIALINFO]
    assert {e.index for e in events} == {1, 2, 3}
    overalls = [e.overall for e in events]
    pairs = zip(overalls, overalls[1:], strict=False)
    assert all(b >= a - 1e-9 for a, b in pairs)  # never goes backwards
    assert overalls[-1] == 1.0


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
