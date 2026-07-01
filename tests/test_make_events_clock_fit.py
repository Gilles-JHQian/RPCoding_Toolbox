"""make-events re-applies a saved clock-drift fit (so re-running it never wipes the correction)."""

from __future__ import annotations

from rpcoding.core import paths
from rpcoding.core.clock_fix import reapply_if_present
from rpcoding.core.config import AppConfig
from rpcoding.core.labels import Interval, Tier, read_tier, write_tier
from rpcoding.core.rpcode.rpcode2trials import save_trials
from rpcoding.core.runner import run_step
from rpcoding.core.session import SubjectSession
from rpcoding.core.steps import Step
from rpcoding.core.tasks import Task
from rpcoding.core.trialinfo.build import save_trialinfo

_TASK = Task.LEXICAL_NODELAY
_AUD = [0, 4, 8, 100, 104, 108]  # Auditory seconds; 2 blocks of 3
_ANCHORS = [(10, "1"), (22, "3"), (200, "4"), (212, "6")]  # true block start/end positions
_DRIFTED = [10, 14, 18, 200, 204, 208]  # cue events generated straight from Auditory
_CORRECTED = [10, 16, 22, 200, 206, 212]  # after the clock-fit (middle trials pulled onto the line)


def _seed_subject(tmp_path, *, with_anchors: bool) -> SubjectSession:
    s = SubjectSession(AppConfig(droot=tmp_path), _TASK, "D9")
    s.results_dir.mkdir(parents=True, exist_ok=True)
    save_trialinfo(
        s.results_dir / paths.TRIALINFO_MAT,
        [
            {"block": float(b), "sound": "x", "cue": "Repeat", "cueStart": float(a)}
            for b, a in zip((1, 1, 1, 2, 2, 2), _AUD, strict=True)
        ],
    )
    d_mat = paths.d_data_subject_dir(tmp_path, _TASK, "D9") / "230101" / "mat"
    d_mat.mkdir(parents=True)
    save_trials(d_mat / "Trials.mat", [{"Trial": i + 1, "Auditory": a * 3e4}
                                       for i, a in enumerate(_AUD)])
    write_tier(
        Tier("first_stims", [Interval(10, 11, "b1"), Interval(200, 201, "b2")]),
        s.results_dir / paths.FIRST_STIMS_TXT,
    )
    if with_anchors:
        write_tier(
            Tier("clock_anchors", [Interval(t, t + 0.05, lab) for t, lab in _ANCHORS]),
            s.results_dir / paths.CLOCK_ANCHORS_TXT,
        )
    return s


def test_make_events_reapplies_clock_fit(tmp_path):
    s = _seed_subject(tmp_path, with_anchors=True)
    run_step(s, Step.MAKE_EVENTS)
    cue = [round(iv.start, 2) for iv in read_tier(s.results_dir / paths.CUE_EVENTS_TXT)]
    assert cue == _CORRECTED  # the saved fit was re-applied, not wiped by the fresh generation


def test_make_events_without_anchors_leaves_events(tmp_path):
    s = _seed_subject(tmp_path, with_anchors=False)
    run_step(s, Step.MAKE_EVENTS)
    cue = [round(iv.start, 2) for iv in read_tier(s.results_dir / paths.CUE_EVENTS_TXT)]
    assert cue == _DRIFTED  # nothing to re-apply -> plain generated events


def test_make_events_reapply_is_idempotent(tmp_path):
    s = _seed_subject(tmp_path, with_anchors=True)
    run_step(s, Step.MAKE_EVENTS)
    run_step(s, Step.MAKE_EVENTS)  # a second pass must reproduce the same corrected events
    cue = [round(iv.start, 2) for iv in read_tier(s.results_dir / paths.CUE_EVENTS_TXT)]
    assert cue == _CORRECTED


def test_reapply_if_present_returns_none_without_anchors_file(tmp_path):
    assert reapply_if_present(tmp_path, tmp_path / "Trials.mat") is None


def test_reapply_if_present_returns_none_when_anchor_file_empty(tmp_path):
    write_tier(Tier("clock_anchors", []), tmp_path / paths.CLOCK_ANCHORS_TXT)
    assert reapply_if_present(tmp_path, tmp_path / "Trials.mat") is None
