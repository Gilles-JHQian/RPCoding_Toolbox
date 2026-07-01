r"""Re-derive misaligned stimulus triggers from the raw ``trigger.mat``, guided by trialInfo.

Some subjects (D84/D86/D90/D139 …) have a corrupted ``Trials.Auditory``: the manual
``maketrigtimes`` step mis-counted the TTL pulses (a stray not zeroed, a missing pulse, or the
double-trigger halving off by one), and ``ecog_preprocessing`` consumes ``trigTimes`` with a single
sequential cursor, so one bad pulse shifts every later trial — a block-level *step* baked into
``Trials.Auditory`` and, from there, into ``cue_events``.

The two ground truths survive that damage: the raw ``trigger.mat`` waveform (all the real pulses are
still in it) and ``trialInfo`` (the experiment computer's authoritative per-trial timing). This
module re-detects the pulses and uses trialInfo's stimulus-time *pattern* as a template to snap each
trial back onto its own true pulse — dropping strays / practice pulses and interpolating a missing
one — recovering a corrected ``Trials.Auditory`` and regenerating the cue/condition events from it.

Detection (threshold, noise zeroing) is the one genuinely per-subject step — mirroring why the lab
ran ``maketrigtimes`` by hand — so the gadget exposes it; the alignment + validation below are
automatic. This is distinct from the clock-drift fix (:mod:`rpcoding.core.clock_fix`): that corrects
a smooth EDF-vs-audio *rate* drift on already-correct triggers; this repairs a *count* error.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from rpcoding.core import paths
from rpcoding.core.events.condition_events import generate_condition_events
from rpcoding.core.events.cue_events import generate_cue_events
from rpcoding.core.matio import (
    load_mat,
    load_trialinfo,
    load_trials,
    trial_audio_onset,
    trial_block,
)
from rpcoding.core.rpcode.rpcode2trials import save_trials

EDF_RATE = 3.0e4  # Trials.Auditory ticks per second
DEFAULT_FREQ = 2048.0  # EDF/amplifier sample rate (Hz) fallback
DEFAULT_THRESH_FRAC = 0.4  # auto threshold = baseline + frac*(robust peak - baseline)
DEFAULT_SNAP_TOL = 1.0  # s: a trial's true pulse must be within this of the predicted position
MIN_PULSE_GAP_S = 0.05  # s: samples closer than this belong to the same pulse
ALIGNED_MS = 100.0  # per-block detrended residual below this counts as aligned
BACKUP_SUFFIX = ".before_trigger_fix"


# --------------------------------------------------------------------------- detection
def auto_threshold(trigger: np.ndarray, frac: float = DEFAULT_THRESH_FRAC) -> float:
    """A robust default detection level: ``median + frac*(p99.9 - median)``.

    The median tracks the quiet baseline and the 99.9th percentile a representative pulse top, so
    the level sits well inside the gap between them and is insensitive to a few saturated samples.
    """
    base = float(np.median(trigger))
    peak = float(np.percentile(trigger, 99.9))
    return base + frac * (peak - base)


def detect_pulses(
    trigger: np.ndarray,
    freq: float,
    thresh: float,
    *,
    zero_regions: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    """Pulse *onset* times (seconds) where ``trigger`` crosses ``thresh``.

    A pulse is a run of above-threshold samples; its onset is the first such sample, and samples
    within ``MIN_PULSE_GAP_S`` of the previous high sample are treated as the same pulse. Any
    ``zero_regions`` (start, end seconds) are blanked first — the tool's equivalent of the manual
    ``to_zero`` noise-clearing in ``maketrigtimes``.
    """
    trigger = np.asarray(trigger, dtype=np.float64).ravel()
    if zero_regions:
        for lo, hi in zero_regions:
            trigger[max(0, int(lo * freq)) : max(0, int(hi * freq))] = float(np.median(trigger))
    high = np.where(trigger >= thresh)[0]
    if high.size == 0:
        return np.empty(0)
    new_pulse = np.diff(high) > MIN_PULSE_GAP_S * freq
    starts = np.concatenate([high[:1], high[1:][new_pulse]])
    return starts / freq


# --------------------------------------------------------------------------- alignment
def _block_index(trialinfo: list[dict]) -> np.ndarray:
    return np.array([int(round(float(trial_block(ti)))) for ti in trialinfo])


def _cue_onsets(trialinfo: list[dict]) -> np.ndarray | None:
    """Per-trial ``cueStart`` (experiment clock) for cue-vs-stimulus disambiguation, or ``None`` if
    any trial lacks it (then anchoring falls back to stimulus-only)."""
    if not all("cueStart" in ti for ti in trialinfo):
        return None
    return np.array([float(ti["cueStart"]) for ti in trialinfo])


def _capped_dist(pulses: np.ndarray, exp: np.ndarray, snap_tol: float) -> np.ndarray:
    """Per-element distance from each ``exp`` time to its nearest pulse, capped at ``snap_tol``."""
    idx = np.clip(np.searchsorted(pulses, exp), 1, len(pulses) - 1)
    d = np.minimum(np.abs(pulses[idx] - exp), np.abs(pulses[idx - 1] - exp))
    return np.minimum(d, snap_tol)


def _anchor(
    pulses: np.ndarray, rel: np.ndarray, snap_tol: float, rel_cue: np.ndarray | None = None
) -> tuple[float, int]:
    """The pulse to place trial 0's stimulus on: the one minimizing the total (tol-capped) distance
    from every ``a0 + rel`` (all trials' expected stimulus times) to its nearest pulse.

    Minimizing *fit tightness* rather than a hit count picks the stimulus pulses over the cue
    pulses: with a double trigger both give a full-length template match, but where the cue→stimulus
    gap *varies* the cue pulses fit ``stimulusAudioStart`` loosely while the stimulus pulses fit to
    detection precision. When the gap is (near-)constant that tie-break vanishes, so — given
    ``rel_cue`` (each trial's cueStart relative to stimulus 0) — the cost also credits a pulse a gap
    *ahead* of each candidate stimulus: only the true stimulus anchor has both its stimulus pulses
    and their cue pulses, so it wins even with a fixed gap (and it's harmless for single-trigger
    subjects — no cue pulses just adds a near-constant term). Capping at ``snap_tol`` keeps strays /
    missing pulses from dominating; a 500-point template needs no per-block anchoring.
    """
    best_a0, best_cost, best_hits = float(pulses[0]), np.inf, 0
    for a0 in pulses:
        ds = _capped_dist(pulses, a0 + rel, snap_tol)
        cost = float(ds.sum())
        if rel_cue is not None:
            cost += float(_capped_dist(pulses, a0 + rel_cue, snap_tol).sum())
        if cost < best_cost:
            best_cost, best_a0 = cost, float(a0)
            best_hits = int(np.count_nonzero(ds < snap_tol))
    return best_a0, best_hits


def _snap(
    pulses: np.ndarray, rel: np.ndarray, a0: float, snap_tol: float
) -> tuple[np.ndarray, np.ndarray]:
    """Walk the trials, snapping each to the nearest pulse to its predicted position.

    The prediction re-anchors to the previous *matched* pulse (``out[i-1] + trialInfo interval``),
    so clock drift is absorbed continuously across the whole recording, block gaps included. A trial
    with no pulse within ``snap_tol`` keeps the interpolated prediction (``matched`` stays False)
    and the walk continues.
    """
    out = np.empty(len(rel))
    matched = np.zeros(len(rel), dtype=bool)
    out[0] = a0
    matched[0] = True
    for i in range(1, len(rel)):
        pred = out[i - 1] + (rel[i] - rel[i - 1])
        j = int(np.searchsorted(pulses, pred))
        cand = [pulses[k] for k in (j - 1, j) if 0 <= k < len(pulses)]
        near = min(cand, key=lambda p: abs(p - pred)) if cand else pred
        if abs(near - pred) < snap_tol:
            out[i], matched[i] = near, True
        else:
            out[i] = pred
    return out, matched


@dataclass
class BlockResidual:
    """Per-block alignment quality (detrended residual of corrected EDF vs trialInfo)."""

    block: int
    n_trials: int
    n_matched: int
    residual_ms: float

    @property
    def aligned(self) -> bool:
        return self.residual_ms <= ALIGNED_MS


@dataclass
class AlignResult:
    """Outcome of aligning pulses to trialInfo."""

    corrected_sec: np.ndarray  # per-trial EDF time (seconds)
    template_hits: int  # trials matched by the global template anchor
    n_matched: int  # trials snapped to a real pulse
    blocks: list[BlockResidual] = field(default_factory=list)

    @property
    def max_residual_ms(self) -> float:
        return max((b.residual_ms for b in self.blocks), default=0.0)

    @property
    def aligned(self) -> bool:
        return all(b.aligned for b in self.blocks)


def is_improvement(align: AlignResult, before_max_ms: float | None) -> bool:
    """Whether keeping the re-derivation is worth it: aligned *and* no worse than the current data.

    Guards the already-clean / irregular-structure case (e.g. D86): if re-derivation can't beat a
    clean ``Trials.Auditory``, the gadget leaves it alone rather than degrade it.
    """
    if not align.aligned:
        return False
    return before_max_ms is None or align.max_residual_ms < before_max_ms


def _residuals(corrected: np.ndarray, audio: np.ndarray, blocks: np.ndarray) -> list[BlockResidual]:
    out: list[BlockResidual] = []
    for b in np.unique(blocks):
        m = blocks == b
        off = audio[m] - corrected[m]
        resid = np.abs(off - np.median(off)).max() * 1000
        out.append(BlockResidual(int(b), int(m.sum()), 0, float(resid)))
    return out


def align_to_trialinfo(
    pulses: np.ndarray,
    audio_onsets: np.ndarray,
    blocks: np.ndarray,
    snap_tol: float = DEFAULT_SNAP_TOL,
    cue_onsets: np.ndarray | None = None,
) -> AlignResult:
    """Recover each trial's true stimulus-pulse EDF time from the detected pulses + trialInfo.

    ``audio_onsets`` are trialInfo's absolute stimulus times (experiment clock) and ``blocks`` the
    per-trial block index. ``cue_onsets`` (trialInfo ``cueStart``), when given, disambiguates the
    stimulus pulses from the cue pulses of the double trigger even when the cue→stimulus gap is
    constant. Anchors once on the full-length template, snaps sequentially, then scores each block
    by the detrended residual of the corrected EDF time against trialInfo.
    """
    audio_onsets = np.asarray(audio_onsets, dtype=np.float64)
    blocks = np.asarray(blocks)
    rel = audio_onsets - audio_onsets[0]
    rel_cue = np.asarray(cue_onsets, dtype=np.float64) - audio_onsets[0] if cue_onsets is not None \
        else None
    a0, hits = _anchor(pulses, rel, snap_tol, rel_cue)
    corrected, matched = _snap(pulses, rel, a0, snap_tol)
    resids = _residuals(corrected, audio_onsets, blocks)
    for br in resids:
        br.n_matched = int(matched[blocks == br.block].sum())
    return AlignResult(corrected, hits, int(matched.sum()), resids)


# --------------------------------------------------------------------------- I/O + apply
def find_trigger_mat(d_data_subject_dir: Path | str) -> Path:
    """Locate the subject's ``**/trigger.mat`` (the extracted EDF DC trigger channel)."""
    base = Path(d_data_subject_dir)
    matches = sorted(base.glob("**/trigger.mat"))
    if not matches:
        raise FileNotFoundError(f"No trigger.mat under {base} (**/trigger.mat)")
    canonical = [m for m in matches if m.parent.name.lower() == "mat"]
    return (canonical or matches)[0]


def read_trigger(path: Path | str) -> np.ndarray:
    """Load the trigger waveform (the ``trigger`` variable) as a 1-D float array."""
    return np.asarray(load_mat(path, simplify=False)["trigger"], dtype=np.float64).ravel()


def read_freq(trigger_path: Path | str, default: float = DEFAULT_FREQ) -> float:
    """The amplifier sample rate from a sibling ``experiment.mat``; ``default`` if unavailable."""
    exp = Path(trigger_path).with_name("experiment.mat")
    if not exp.exists():
        return default
    try:
        e = load_mat(exp, simplify=True)["experiment"]
        rate = e["recording"]["sample_rate"]
        return float(np.asarray(rate).ravel()[0])
    except (KeyError, IndexError, ValueError, TypeError):
        return default


def _backup(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)


def _write_corrected_trials(trials: list[dict], corrected_sec: np.ndarray, out: Path) -> None:
    """Write a copy of ``trials`` with ``Auditory`` replaced by the corrected EDF times (30 kHz
    ticks), preserving every other field. Backs up an existing file first."""
    fixed: list[dict] = []
    for tr, sec in zip(trials, corrected_sec, strict=True):
        t = dict(tr)
        ticks = sec * EDF_RATE
        t["Auditory"] = type(tr["Auditory"])(ticks) if "Auditory" in tr else ticks
        fixed.append(t)
    _backup(out)
    save_trials(out, fixed)


@dataclass
class TriggerFixReport:
    """What :func:`apply_trigger_fix` did, for the GUI / logs."""

    n_pulses: int
    n_trials: int
    align: AlignResult
    trials_path: Path
    events_regenerated: bool
    before_max_ms: float | None = None  # current Trials.Auditory residual, if it was readable

    @property
    def aligned(self) -> bool:
        return self.align.aligned

    @property
    def improved(self) -> bool:
        return is_improvement(self.align, self.before_max_ms)


def preview_alignment(
    results_dir: Path | str,
    d_data_subject_dir: Path | str,
    *,
    thresh: float | None = None,
    thresh_frac: float = DEFAULT_THRESH_FRAC,
    zero_regions: list[tuple[float, float]] | None = None,
    snap_tol: float = DEFAULT_SNAP_TOL,
    trials_mat: Path | str | None = None,
) -> tuple[np.ndarray, float, AlignResult, float | None]:
    """Detect + align without writing anything (for the interactive review).

    Returns ``(pulse_times, threshold_used, align_result, before_max_ms)`` where ``before_max_ms``
    is the current ``Trials.Auditory`` residual (so the UI can show before/after), or ``None`` if
    the current Trials can't be read / length-matched.
    """
    results_dir = Path(results_dir)
    trialinfo = load_trialinfo(results_dir / paths.TRIALINFO_MAT)
    audio = np.array([float(trial_audio_onset(ti)) for ti in trialinfo])
    blocks = _block_index(trialinfo)

    trig_path = find_trigger_mat(d_data_subject_dir)
    freq = read_freq(trig_path)
    trigger = read_trigger(trig_path)
    level = thresh if thresh is not None else auto_threshold(trigger, thresh_frac)
    pulses = detect_pulses(trigger, freq, level, zero_regions=zero_regions)
    align = align_to_trialinfo(pulses, audio, blocks, snap_tol, cue_onsets=_cue_onsets(trialinfo))

    before = None
    if trials_mat is not None:
        try:
            trials = load_trials(trials_mat)
            if len(trials) == len(trialinfo):
                cur = np.array([float(tr["Auditory"]) / EDF_RATE for tr in trials])
                before = max(b.residual_ms for b in _residuals(cur, audio, blocks))
        except (KeyError, ValueError, OSError):
            before = None
    return pulses, level, align, before


def apply_trigger_fix(
    results_dir: Path | str,
    d_data_subject_dir: Path | str,
    trials_mat: Path | str,
    *,
    thresh: float | None = None,
    thresh_frac: float = DEFAULT_THRESH_FRAC,
    zero_regions: list[tuple[float, float]] | None = None,
    snap_tol: float = DEFAULT_SNAP_TOL,
    regenerate_events: bool = True,
) -> TriggerFixReport:
    """Detect pulses, align to trialInfo, write the corrected ``Auditory`` back into ``trials_mat``,
    and (optionally) regenerate ``cue_events`` / ``condition_events`` from it.

    The correction is written **in place** at ``trials_mat`` (the canonical D_Data
    ``<date>/mat/Trials.mat``), backing the original up to ``Trials.mat.before_trigger_fix`` once,
    so the shared dataset the downstream events.tsv pipeline reads carries the fix. If write-Trials
    already ran, its pristine source ``Trials_org.mat`` still holds the bad triggers, so it is
    corrected too (else a re-run would restore them). Requires ``trialInfo.mat`` (and, to regenerate
    events, ``first_stims.txt``) in ``results_dir``. Raises ``ValueError`` on a Trials/trialInfo
    length mismatch.
    """
    results_dir = Path(results_dir)
    trialinfo = load_trialinfo(results_dir / paths.TRIALINFO_MAT)
    audio = np.array([float(trial_audio_onset(ti)) for ti in trialinfo])
    blocks = _block_index(trialinfo)

    trials = load_trials(trials_mat)
    if len(trials) != len(trialinfo):
        raise ValueError(
            f"Trials ({len(trials)}) and trialInfo ({len(trialinfo)}) length mismatch — "
            "resolve that before fixing triggers."
        )

    trig_path = find_trigger_mat(d_data_subject_dir)
    freq = read_freq(trig_path)
    trigger = read_trigger(trig_path)
    level = thresh if thresh is not None else auto_threshold(trigger, thresh_frac)
    pulses = detect_pulses(trigger, freq, level, zero_regions=zero_regions)
    align = align_to_trialinfo(pulses, audio, blocks, snap_tol, cue_onsets=_cue_onsets(trialinfo))

    cur = np.array([float(tr["Auditory"]) / EDF_RATE for tr in trials])
    before_max = max(b.residual_ms for b in _residuals(cur, audio, blocks))

    out = Path(trials_mat)  # write the correction back into D_Data, in place (original backed up)
    _write_corrected_trials(trials, align.corrected_sec, out)
    org = out.with_name("Trials_org.mat")  # write-Trials' pristine source, if it already ran
    if org.exists():
        org_trials = load_trials(org)
        if len(org_trials) == len(align.corrected_sec):
            _write_corrected_trials(org_trials, align.corrected_sec, org)

    regenerated = False
    if regenerate_events and (results_dir / paths.FIRST_STIMS_TXT).exists():
        _backup(results_dir / paths.CUE_EVENTS_TXT)
        _backup(results_dir / paths.CONDITION_EVENTS_TXT)
        generate_cue_events(results_dir, out)
        generate_condition_events(results_dir)
        regenerated = True

    return TriggerFixReport(
        n_pulses=len(pulses),
        n_trials=len(trials),
        align=align,
        trials_path=out,
        events_regenerated=regenerated,
        before_max_ms=before_max,
    )
