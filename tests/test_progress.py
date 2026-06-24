"""Tests for the lightweight progress protocol (rpcoding.core.progress)."""

from __future__ import annotations

from rpcoding.core.progress import StepProgress, clamp01, noop, sub
from rpcoding.core.steps import Step


def test_noop_accepts_anything():
    assert noop(0.5, "x") is None
    assert noop(None, "") is None


def test_clamp01():
    assert clamp01(-0.2) == 0.0
    assert clamp01(1.5) == 1.0
    assert clamp01(0.3) == 0.3


def test_sub_maps_into_subrange_and_passes_none():
    seen: list = []
    child = sub(lambda f, m: seen.append((f, m)), 0.0, 0.8)
    child(0.5, "half")
    assert seen[-1] == (0.4, "half")  # 0.5 of [0, 0.8]
    child(1.0, "full")
    assert seen[-1] == (0.8, "full")
    child(None, "busy")  # indeterminate stays indeterminate
    assert seen[-1] == (None, "busy")


def test_sub_clamps_out_of_range_input():
    seen: list = []
    sub(lambda f, m: seen.append(f), 0.2, 0.6)(2.0, "over")
    assert seen[-1] == 0.6  # 0.2 + clamp01(2.0) * 0.4


def test_sub_tolerates_none_parent():
    # A None parent reporter must not blow up (defaults to noop).
    sub(None, 0.0, 1.0)(0.5, "x")


def test_step_progress_overall():
    sp = StepProgress(step=Step.CONCAT_WAVS, index=2, total=4, fraction=0.5, message="x", title="t")
    # base (2-1)/4 = 0.25 ; + 0.5/4 = 0.125 => 0.375
    assert sp.overall == 0.375


def test_step_progress_overall_indeterminate_and_zero_total():
    sp = StepProgress(Step.RUN_MFA, index=1, total=3, fraction=None, message="m", title="MFA")
    assert sp.overall == 0.0  # base (1-1)/3 = 0, indeterminate adds nothing
    assert StepProgress(Step.RUN_MFA, 1, 0, 0.5, "m", "MFA").overall == 0.0  # guard against /0
