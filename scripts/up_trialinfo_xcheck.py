r"""Second-round UP health-check: Trials.mat vs trialInfo per-trial timing (see §2.6/§5.1 of docs).

This is the *authoritative* alignment check. ``trialInfo`` (built from the per-block TrialData) is
the experiment computer's own log — one entry per trial actually run, with real-clock onset times
``cueStart`` / ``stimulusAudioStart``. ``Trials.mat`` carries the EDF-derived ``Start`` /
``Auditory`` ticks (@30 kHz) filled by sequentially consuming trigTimes. The two clocks differ in
origin but run at the same rate, so trial-for-trial they must track.

For each block we subtract the block's median (trialInfo_onset - Trials_onset) offset and look at
the per-trial residual. A correctly aligned trial sits within clock jitter (~15 ms on clean); a
trigger miscount makes the residual step to hundreds of ms — seconds, and pinpoints the exact trial
where the block goes off (which the geometric boundary check can only see at block granularity).

Unlike the first-round geometric check, this also catches a missing+stray trigger that cancels
within a block (block still holds 120 trials, but the trials inside are shuffled).

Run:  python scripts/up_trialinfo_xcheck.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from rpcoding.core import paths
from rpcoding.core.matio import load_trials
from rpcoding.core.tasks import Task
from rpcoding.core.trialinfo.build import (
    IncompleteTrialInfoError,
    discover_trialdata_files,
    select_and_combine,
)
from rpcoding.gui.config import load_config

EDF_RATE = 3.0e4
THRESH = 0.100  # seconds; a per-trial residual above this = misaligned (clean jitter ~0.015s)


class Status:
    OK = "OK"
    MISALIGNED = "MISALIGNED"  # per-trial timing diverges from trialInfo
    LEN_MISMATCH = "LEN_MISMATCH"  # len(Trials) != len(trialInfo): cue_events can't even build
    NO_TRIALINFO = "NO_TRIALINFO"  # TrialData not downloaded / can't combine
    UNAVAILABLE = "UNAVAILABLE"  # no Trials.mat


def _subject_dirs(droot: Path) -> list[str]:
    base = paths.d_data_dir(droot, "Uniqueness_Point")
    out: list[str] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name.lower().startswith("old_") or d.name.lower() == "edfs":
            continue
        tok = d.name.split()[0]
        if tok.startswith("D") and tok[1:].isdigit():
            out.append(tok)
    return out


def _find_trials_mat(subject_dir: Path) -> Path | None:
    matches: list[Path] = []
    for root, _dirs, files in os.walk(subject_dir, onerror=lambda e: None):
        if Path(root).name.lower() == "mat" and "Trials.mat" in files:
            matches.append(Path(root) / "Trials.mat")
    if not matches:
        return None
    canonical = [m for m in matches if paths._is_canonical_trials(m, subject_dir)]
    return (canonical or sorted(matches))[0]


def _onsets(records: list[dict], field: str, *, edf: bool) -> np.ndarray:
    vals = np.array([float(r[field]) for r in records])
    return vals / EDF_RATE if edf else vals


def _residual_report(blk: np.ndarray, ti_on: np.ndarray, tr_on: np.ndarray) -> dict:
    """Per-block offset-removed residual; returns max-ms, onset trial, and bad-count per block."""
    n = len(blk)
    resid = np.zeros(n)
    for b in np.unique(blk):
        m = blk == b
        resid[m] = (ti_on[m] - tr_on[m]) - np.median(ti_on[m] - tr_on[m])
    blocks: list[dict] = []
    for b in np.unique(blk):
        idx = np.where(blk == b)[0]
        r = np.abs(resid[idx])
        bad = [int(i + 1) for i in idx if r[idx == i].size and np.abs(resid[i]) >= THRESH]
        blocks.append(
            {
                "block": int(b),
                "max_ms": float(r.max() * 1000),
                "n_bad": len(bad),
                "onset": bad[0] if bad else None,
            }
        )
    return {"resid": resid, "blocks": blocks, "max_ms": max(x["max_ms"] for x in blocks)}


def _analyze(subj: str, droot: Path) -> dict:
    sdir_dd = paths.d_data_subject_dir(droot, "Uniqueness_Point", subj)
    tmat = _find_trials_mat(sdir_dd)
    if tmat is None:
        return {"status": Status.UNAVAILABLE, "detail": "no Trials.mat"}
    try:
        trials = load_trials(tmat)
    except (OSError, ValueError, KeyError) as e:
        return {"status": Status.UNAVAILABLE, "detail": f"unreadable: {type(e).__name__}"}

    sdir = paths.cogan_subject_dir(droot, subj)
    try:
        blocks_dir = paths.resolve_blocks_dir(sdir, Task.UNIQUENESS_POINT)
        files = discover_trialdata_files(blocks_dir)
        ti, _info = select_and_combine(files)
    except (IncompleteTrialInfoError, OSError, ValueError, KeyError) as e:
        return {
            "status": Status.NO_TRIALINFO,
            "detail": f"{type(e).__name__}: {e}",
            "n_tr": len(trials),
        }

    if len(ti) != len(trials):
        return {
            "status": Status.LEN_MISMATCH,
            "detail": f"len(trialInfo)={len(ti)} != len(Trials)={len(trials)}",
            "n_ti": len(ti),
            "n_tr": len(trials),
        }

    n = len(ti)
    blk = np.array([int(round(float(t["block"]))) for t in ti])
    rep = _residual_report(
        blk,
        _onsets(ti, "stimulusAudioStart", edf=False),
        _onsets(trials, "Auditory", edf=True),
    )
    status = Status.MISALIGNED if rep["max_ms"] >= THRESH * 1000 else Status.OK
    return {"status": status, "n": n, "rep": rep}


def main() -> int:
    cfg = load_config()
    if cfg is None:
        print("No app config found.", file=sys.stderr)
        return 2
    droot = Path(cfg.droot)
    print(f"droot = {droot}")
    print(f"threshold = {THRESH * 1000:.0f} ms per-trial residual (clean subjects sit ~15 ms)\n")

    rows = [(s, _analyze(s, droot)) for s in _subject_dirs(droot)]
    order = {
        Status.LEN_MISMATCH: 0,
        Status.MISALIGNED: 1,
        Status.NO_TRIALINFO: 2,
        Status.UNAVAILABLE: 3,
        Status.OK: 4,
    }
    rows.sort(key=lambda r: (order[r[1]["status"]], r[0]))

    print(f"{'subj':<6}{'status':<14}detail")
    print("-" * 100)
    for subj, r in rows:
        if r["status"] in (Status.MISALIGNED, Status.OK):
            rep = r["rep"]
            parts = []
            for b in rep["blocks"]:
                tag = f"b{b['block']}:{b['max_ms']:.0f}ms"
                if b["onset"] is not None:
                    tag += f"(from t{b['onset']}, {b['n_bad']}bad)"
                parts.append(tag)
            print(f"{subj:<6}{r['status']:<14}max {rep['max_ms']:.0f}ms | " + "  ".join(parts))
        else:
            print(f"{subj:<6}{r['status']:<14}{r.get('detail','')}")

    def ids(st: str) -> list[str]:
        return [s for s, r in rows if r["status"] == st]

    print("\n" + "=" * 70)
    print("SUMMARY (authoritative trialInfo cross-check)")
    for st in (
        Status.LEN_MISMATCH,
        Status.MISALIGNED,
        Status.OK,
        Status.NO_TRIALINFO,
        Status.UNAVAILABLE,
    ):
        got = ids(st)
        print(f"  {st:<13} ({len(got):>2}): {', '.join(got) if got else '—'}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
