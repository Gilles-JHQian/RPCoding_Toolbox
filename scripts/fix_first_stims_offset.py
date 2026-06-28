r"""One-shot: correct first_stims.txt for the spectrogram frame-centre display offset.

Marks placed against the (previously ~17 ms-early) spectrogram sit early by
``frame_time_offset(n_fft, hop, fs)`` seconds; this shifts each subject's onsets *later* by that
amount, computed from the subject's own ``allblocks.wav`` sample rate. Backs up every file first and
writes an idempotency marker (so a re-run is a no-op). Use ``--restore`` to undo from the backups.

    python scripts/fix_first_stims_offset.py            # apply
    python scripts/fix_first_stims_offset.py --restore  # undo

The target subjects are the ones whose first_stims were marked with this software in the last few
days (see the offset-fix discussion / CHANGELOG entry).
"""

from __future__ import annotations

import sys
from pathlib import Path

import soundfile as sf

from rpcoding.core.audio.render.spectro import StftParams, frame_time_offset
from rpcoding.core.first_stims_offset import apply_first_stims_offset, restore_first_stims

RESULTS = Path(
    "F:/CloudStorage/Box/CoganLab/ECoG_Task_Data/response_coding/response_coding_results"
)

# (task, subject) marked with this software in the recent session.
TARGETS: list[tuple[str, str]] = [
    *[
        ("Uniqueness_Point", s)
        for s in (
            "D28",
            "D29",
            "D42",
            "D54",
            "D57",
            "D59",
            "D63",
            "D69",
            "D71",
            "D86",
            "D90",
            "D92",
            "D94",
            "D100",
            "D102",
            "D117",
            "D121",
            "D130",
            "D134",
            "D139",
            "D142",
            "D144",
            "D147",
        )
    ],
    *[("LexicalDecRepNoDelay", s) for s in ("D142", "D144", "D145", "D146")],
]

_PARAMS = StftParams()


def _offset_for(results_dir: Path) -> tuple[float, int | None]:
    """frame_time_offset from the subject's allblocks.wav fs (fallback 44100 if unreadable)."""
    try:
        fs = sf.info(str(results_dir / "allblocks.wav")).samplerate
    except (OSError, RuntimeError):
        fs = 44100
        return frame_time_offset(_PARAMS.n_fft, _PARAMS.hop, fs), None
    return frame_time_offset(_PARAMS.n_fft, _PARAMS.hop, fs), fs


def main(restore: bool) -> int:
    rows: list[str] = []
    n_changed = 0
    for task, subj in TARGETS:
        rd = RESULTS / task / subj
        if restore:
            res = restore_first_stims(rd)
            rows.append(f"{task:<22}{subj:<7}{res['status']}")
            n_changed += res["status"] == "restored"
            continue
        off, fs = _offset_for(rd)
        res = apply_first_stims_offset(rd, off, reason="spectrogram_frame_center_17ms")
        fs_txt = f"{fs} Hz" if fs else "fs? (default 44100)"
        extra = ""
        if res["status"] != "no_first_stims":
            extra = f"  +{off * 1000:.2f} ms  ({fs_txt}, n={res.get('n', '-')})"
        rows.append(f"{task:<22}{subj:<7}{res['status']:<16}{extra}")
        n_changed += res["status"] == "applied"

    out = Path(sys.argv[0]).with_name("fix_first_stims_offset_report.txt")
    action = "RESTORE" if restore else "APPLY"
    header = f"{action} — {n_changed} changed / {len(TARGETS)} targets"
    out.write_text(header + "\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(header)
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(restore="--restore" in sys.argv[1:]))
