r"""Health-check Uniqueness_Point subjects' upstream Trials.mat.

See docs/irregular_subjects.md §5.1. This is the data-driven "体检" that answers *which UP
subjects look irregular*, since MATLAB keeps no per-subject list for the Layer-A (trigger
extraction) problems.

Self-contained: reads ONLY the small, already-downloaded ``**/mat/Trials.mat`` per subject —
no trialInfo, no block wavs, and it never writes to the CoganLab dataset. It looks for the
Layer-A failure modes that bake bad ``Trials.Auditory`` into the upstream data:

  * length not a multiple of 120          (UP = 4 blocks x 120 = 480)
  * non-monotonic Auditory ticks          (trigger ordering broken)
  * Start->Auditory intra-trial outliers  (a trial's Start/Auditory pairing broke)
  * block-pause gaps not at 120/240/360    (off-by-k trigger misalignment — D90/D86 type)
  * large within-block gaps                (mid-block recording jumps — D42 type)
  * abnormally tight gaps                   (residual double triggers / compressed timing)

Run:  python scripts/up_trials_healthcheck.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

from rpcoding.core import paths
from rpcoding.core.matio import load_trials
from rpcoding.gui.config import load_config

EDF_RATE = 3.0e4  # EDF clock ticks per second
BLOCK_SIZE = 120  # UP: trials per block

# --- thresholds (calibrated on D100/D94/D28 clean vs D86/D90/D42 broken) ---
INTRA_LO, INTRA_HI = 1.2, 2.3  # plausible Start->Auditory seconds (observed 1.53–1.82)
BOUNDARY_FLOOR = 7.0  # a gap >= this (or median+8*MAD) is an inter-block pause, not a trial
BOUNDARY_NEAR = 3  # an extra big gap within this many trials of a nominal boundary = "shifted"
TIGHT_GAP = 2.5  # inter-trial gap below this is unusually tight (clean subjects: min ~2.9s)


class Status:
    OK = "OK"
    INTERRUPTED = "INTERRUPTED"  # big within-block pauses, but block boundaries intact (align OK)
    MISALIGNED = "MISALIGNED"  # nominal boundary missing/shifted or wrong length (align broken)
    UNAVAILABLE = "UNAVAILABLE"


def _subject_dirs(droot: Path) -> list[tuple[str, Path]]:
    """(subject_id, dir) for every D### folder under D_Data/Uniqueness_Point."""
    base = paths.d_data_dir(droot, "Uniqueness_Point")
    out: list[tuple[str, Path]] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        if name.lower().startswith("old_") or name.lower() == "edfs":
            continue
        # subject id is the leading D### token ("D82 (No Trigs)" -> D82)
        tok = name.split()[0]
        if tok.startswith("D") and tok[1:].isdigit():
            out.append((tok, d))
    return out


def _find_trials_mat(subject_dir: Path) -> Path | None:
    """Locate ``**/mat/Trials.mat`` under a subject dir, tolerant of cloud-placeholder OSErrors.

    pathlib.glob() stats every entry and explodes on Box online-only placeholders (WinError 1006),
    so walk manually and skip unreadable entries. Prefer the canonical ``<date>/mat/Trials.mat``.
    """
    matches: list[Path] = []
    for root, _dirs, files in os.walk(subject_dir, onerror=lambda e: None):
        if Path(root).name.lower() != "mat":
            continue
        if "Trials.mat" in files:
            matches.append(Path(root) / "Trials.mat")
    if not matches:
        return None
    canonical = [m for m in matches if paths._is_canonical_trials(m, subject_dir)]
    return (canonical or sorted(matches))[0]


def _analyze(trials: list[dict]) -> dict:
    """Run the Trials.Auditory geometry checks; return a result dict with status + reasons."""
    n = len(trials)
    aud = np.array([float(t["Auditory"]) for t in trials])
    start = np.array([float(t["Start"]) for t in trials])
    res: dict = {"n": n, "reasons": [], "status": Status.OK, "boundaries": ""}

    def escalate(to: str) -> None:
        rank = {Status.OK: 0, Status.INTERRUPTED: 1, Status.MISALIGNED: 2}
        if rank[to] > rank[res["status"]]:
            res["status"] = to

    # 1) length a clean multiple of 120
    if n == 0:
        res["status"] = Status.UNAVAILABLE
        res["reasons"].append("empty Trials")
        return res
    nblocks = n // BLOCK_SIZE
    if n % BLOCK_SIZE != 0:
        escalate(Status.MISALIGNED)
        res["reasons"].append(f"len {n} not a multiple of {BLOCK_SIZE} (expected 480)")
    elif n != 480:
        res["reasons"].append(f"len {n} ({nblocks} blocks, not the usual 480)")

    # 2) Auditory strictly increasing
    d = np.diff(aud) / EDF_RATE  # gap between trial j and j+1 lives at d[j-1]
    if (d <= 0).any():
        bad = [int(i + 1) for i in np.where(d <= 0)[0]]
        escalate(Status.MISALIGNED)
        res["reasons"].append(f"Auditory not increasing after trial(s) {bad[:8]}")

    # 3) Start->Auditory intra-trial interval outliers (a trial's Start/Auditory pairing broke)
    intra = (aud - start) / EDF_RATE
    med = float(np.median(intra))
    bad_intra = [int(i + 1) for i in np.where((intra < INTRA_LO) | (intra > INTRA_HI))[0]]
    if bad_intra:
        escalate(Status.MISALIGNED)
        res["reasons"].append(
            f"{len(bad_intra)} trial(s) with odd Start->Auditory gap "
            f"(median {med:.2f}s) e.g. {bad_intra[:6]}"
        )

    # 4) block-boundary alignment. A nominal boundary (120/240/360) must carry an inter-block
    #    pause. If it does, the block holds its 120 trials and trial<->trialInfo alignment is
    #    preserved even when the recording was paused mid-block. A nominal boundary with NO pause
    #    (its pause sits a trial or two off, or is absent) is the off-by-k trigger misalignment.
    if n % BLOCK_SIZE == 0 and (d > 0).all() and nblocks > 1:
        mad = float(np.median(np.abs(d - np.median(d)))) or 0.0
        thr = max(BOUNDARY_FLOOR, float(np.median(d)) + 8.0 * mad)
        large_pos = {int(i + 1) for i in np.where(d > thr)[0]}  # trials whose gap-to-next is big
        expected = {BLOCK_SIZE * k for k in range(1, nblocks)}
        missing = sorted(expected - large_pos)  # nominal boundaries with no pause
        unexplained = sorted(large_pos - expected)  # big gaps not on a nominal boundary
        res["boundaries"] = (
            f"big-gap@{sorted(large_pos)}  nominal@{sorted(expected)} (thr {thr:.1f}s)"
        )

        # a missing boundary is "shifted" if a big gap sits within BOUNDARY_NEAR of it
        shifts = []
        for b in missing:
            near = [j for j in unexplained if abs(j - b) <= BOUNDARY_NEAR]
            if near:
                j = min(near, key=lambda x: abs(x - b))  # noqa: B023
                shifts.append(f"{b}->{j}({j - b:+d}, {d[j - 1]:.0f}s)")
                unexplained.remove(j)
        unshifted = [b for b in missing if not any(str(b) + "->" in s for s in shifts)]

        if missing:
            escalate(Status.MISALIGNED)
            if shifts:
                res["reasons"].append(f"boundary shifted: {', '.join(shifts)}")
            if unshifted:
                res["reasons"].append(f"no inter-block pause at nominal boundary {unshifted}")
        if unexplained:  # big gaps deep inside a block: recording pause, alignment intact
            escalate(Status.INTERRUPTED)
            mid = ", ".join(f"{j}({d[j - 1]:.0f}s)" for j in unexplained)
            res["reasons"].append(f"within-block pause(s) [boundaries intact]: {mid}")

    # 5) unusually tight inter-trial gaps (residual double triggers / compressed timing)
    if (d > 0).all():
        tight = [(int(i + 1), round(float(d[i]), 2)) for i in np.where(d < TIGHT_GAP)[0]]
        if tight:
            escalate(Status.INTERRUPTED)
            res["reasons"].append(f"tight gap(s) <{TIGHT_GAP}s (double-trig residue?): {tight[:8]}")

    return res


def main() -> int:
    cfg = load_config()
    if cfg is None:
        print("No app config found; cannot locate droot.", file=sys.stderr)
        return 2
    droot = Path(cfg.droot)
    print(f"droot = {droot}")
    print(f"scanning {paths.d_data_dir(droot, 'Uniqueness_Point')}\n")

    rows: list[tuple[str, dict]] = []
    for subj, sdir in _subject_dirs(droot):
        tmat = _find_trials_mat(sdir)
        if tmat is None:
            rows.append(
                (
                    subj,
                    {
                        "status": Status.UNAVAILABLE,
                        "n": 0,
                        "reasons": ["no Trials.mat under **/mat/ (not downloaded?)"],
                        "boundaries": "",
                    },
                )
            )
            continue
        try:
            trials = load_trials(tmat)
        except (OSError, ValueError, KeyError) as e:
            rows.append(
                (
                    subj,
                    {
                        "status": Status.UNAVAILABLE,
                        "n": 0,
                        "reasons": [f"unreadable (cloud placeholder?): {type(e).__name__}"],
                        "boundaries": "",
                    },
                )
            )
            continue
        res = _analyze(trials)
        res["file"] = str(tmat)
        rows.append((subj, res))

    # ---- report ----
    order = {Status.MISALIGNED: 0, Status.INTERRUPTED: 1, Status.UNAVAILABLE: 2, Status.OK: 3}
    rows.sort(key=lambda r: (order[r[1]["status"]], r[0]))

    print(f"{'subj':<6}{'status':<13}{'n':>5}  detail")
    print("-" * 100)
    for subj, r in rows:
        detail = "; ".join(r["reasons"]) if r["reasons"] else "clean"
        print(f"{subj:<6}{r['status']:<13}{r['n']:>5}  {detail}")
        if r.get("boundaries") and r["status"] in (Status.MISALIGNED, Status.INTERRUPTED):
            print(f"{'':>24} {r['boundaries']}")

    # ---- summary ----
    def ids(st: str) -> list[str]:
        return [s for s, r in rows if r["status"] == st]

    print("\n" + "=" * 70)
    print("SUMMARY  (MISALIGNED = block boundary off / wrong length -> cue_events WILL be wrong;")
    print("          INTERRUPTED = recording paused mid-block but boundaries intact -> review)")
    for st in (Status.MISALIGNED, Status.INTERRUPTED, Status.OK, Status.UNAVAILABLE):
        got = ids(st)
        print(f"  {st:<12} ({len(got):>2}): {', '.join(got) if got else '—'}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
