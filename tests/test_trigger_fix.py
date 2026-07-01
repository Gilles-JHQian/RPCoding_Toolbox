"""Unit tests for core.trigger_fix: pulse detection + trialInfo-guided stimulus-trigger recovery."""

from __future__ import annotations

import numpy as np
import pytest

from rpcoding.core.trigger_fix import (
    _residuals,
    align_to_trialinfo,
    auto_threshold,
    detect_pulses,
    is_improvement,
)

FREQ = 100.0  # Hz — tiny synthetic sample rate


# ----- a synthetic double-trigger recording (cue + stimulus pulse per trial) -----
def _double_trigger_case():
    """Two blocks of 5 trials. EDF stimulus time = experiment audio - a constant; a cue pulse sits a
    *variable* ~2 s ahead of each stimulus (cue pulses fit trialInfo loosely, stimulus tightly)."""
    audio = np.array([100.0, 104.0, 108.0, 112.5, 117.0, 200.0, 205.0, 209.0, 213.0, 218.0])
    blocks = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2])
    const = 50.0
    edf_stim = audio - const  # true stimulus-pulse EDF times
    gaps = 2.0 + np.array([0.18, -0.2, 0.15, -0.17, 0.2, -0.18, 0.16, -0.2, 0.19, -0.15])
    edf_cue = edf_stim - gaps
    return audio, blocks, edf_stim, edf_cue


def test_detect_pulses_finds_onsets():
    sig = np.full(1000, 5.0)
    for lo, hi in [(100, 106), (300, 309), (500, 504)]:  # three pulses
        sig[lo:hi] = 90.0
    onsets = detect_pulses(sig, FREQ, thresh=50.0)
    assert np.allclose(onsets, [1.0, 3.0, 5.0])


def test_detect_pulses_zero_regions_blank_noise():
    sig = np.full(1000, 5.0)
    for lo, hi in [(100, 106), (300, 309), (500, 504)]:
        sig[lo:hi] = 90.0
    onsets = detect_pulses(sig, FREQ, thresh=50.0, zero_regions=[(2.9, 3.2)])  # blank middle pulse
    assert np.allclose(onsets, [1.0, 5.0])


def test_auto_threshold_between_baseline_and_peak():
    sig = np.full(1000, 5.0)
    sig[100:110] = 100.0
    thr = auto_threshold(sig)
    assert 5.0 < thr < 100.0


def test_align_locks_onto_stimulus_not_cue_pulses():
    audio, blocks, edf_stim, edf_cue = _double_trigger_case()
    pulses = np.sort(np.concatenate([edf_cue, edf_stim, [30.5, 90.0]]))  # + 2 strays
    res = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0)
    assert res.aligned
    assert res.n_matched == 10
    # recovers the stimulus pulses (audio - const), NOT the cue pulses ~2 s earlier
    assert np.allclose(res.corrected_sec, edf_stim, atol=1e-6)


def test_align_constant_gap_uses_cue_to_pick_stimulus():
    """With a *fixed* cue→stimulus gap, stimulus and cue pulses fit the template equally; cueStart
    breaks the tie so we still lock onto the stimulus (not the cue) pulses."""
    audio, blocks, edf_stim, _ = _double_trigger_case()
    const_gap = 2.0
    edf_cue = edf_stim - const_gap  # perfectly constant gap
    cue_onsets = audio - const_gap  # trialInfo cueStart mirrors it
    pulses = np.sort(np.concatenate([edf_cue, edf_stim]))
    # stimulus-only anchoring is ambiguous here (would grab the earlier cue pulses)...
    without_cue = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0)
    assert np.allclose(without_cue.corrected_sec, edf_cue, atol=1e-6)
    # ...but with cueStart it recovers the true stimulus pulses
    with_cue = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0, cue_onsets=cue_onsets)
    assert np.allclose(with_cue.corrected_sec, edf_stim, atol=1e-6)


def test_align_interpolates_a_missing_stimulus_pulse():
    audio, blocks, edf_stim, edf_cue = _double_trigger_case()
    kept = np.delete(edf_stim, 3)  # trial 3's stimulus pulse is missing
    pulses = np.sort(np.concatenate([edf_cue, kept]))
    res = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0)
    assert res.aligned
    assert res.n_matched == 9  # trial 3 has no pulse...
    assert np.allclose(res.corrected_sec, edf_stim, atol=1e-6)  # ...but is interpolated exactly


def test_align_is_drift_tolerant():
    """A per-trial clock drift between the experiment and EDF clocks is absorbed by re-anchoring."""
    audio, blocks, edf_stim, edf_cue = _double_trigger_case()
    drift = 1e-3 * np.arange(len(audio))  # up to 9 ms of accumulating drift
    pulses = np.sort(np.concatenate([edf_cue, edf_stim + drift]))
    res = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0)
    assert res.aligned
    assert np.allclose(res.corrected_sec, edf_stim + drift, atol=1e-6)


def test_improvement_guard():
    audio, blocks, edf_stim, edf_cue = _double_trigger_case()
    jit = np.array([0.03, -0.05, 0.04, -0.03, 0.05, -0.04, 0.03, -0.05, 0.04, -0.03])
    pulses = np.sort(np.concatenate([edf_cue, edf_stim + jit]))  # ~tens of ms of detection jitter
    res = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0)
    assert res.aligned
    after = res.max_residual_ms
    assert 10.0 < after < 100.0  # aligned, but not pixel-perfect
    assert is_improvement(res, before_max_ms=2000.0)  # fixes a badly misaligned current file
    assert not is_improvement(res, before_max_ms=after / 2)  # current is cleaner -> leave it
    assert is_improvement(res, before_max_ms=None)  # unknown current -> take the aligned result


def test_recovers_a_block_step_misalignment():
    """The canonical failure: a dropped trigger shifts every later trial in a block by ~one slot."""
    audio, blocks, edf_stim, edf_cue = _double_trigger_case()
    pulses = np.sort(np.concatenate([edf_cue, edf_stim]))
    res = align_to_trialinfo(pulses, audio, blocks, snap_tol=1.0)

    # a corrupted Trials.Auditory where block 1 trials 2.. were read off-by-one (shifted late)
    bad = edf_stim.copy()
    bad[2:5] = edf_stim[3:6]  # slot slip within block 1
    before = max(b.residual_ms for b in _residuals(bad, audio, blocks))
    after = res.max_residual_ms
    assert before > 100.0 and after < 10.0
    assert is_improvement(res, before)


def test_align_rejects_length_zero_pulses_gracefully():
    audio, blocks, _edf_stim, _edf_cue = _double_trigger_case()
    with pytest.raises((IndexError, ValueError)):
        align_to_trialinfo(np.empty(0), audio, blocks)
