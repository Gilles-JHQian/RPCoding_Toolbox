r"""One-shot time correction for ``first_stims.txt``.

Marks placed against the spectrogram inherited its frame-centre display offset
(:func:`rpcoding.core.audio.render.spectro.frame_time_offset`), so the onsets sit early by a
constant. This shifts every onset by that constant, keeping a backup and an idempotency marker so
the correction can't be applied twice; :func:`restore_first_stims` undoes it from the backup.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rpcoding.core.labels import Interval, Tier, read_tier, write_tier

FIRST_STIMS = "first_stims.txt"
BACKUP_NAME = "first_stims.before_offset_fix.txt"
MARKER_REL = ".rpcoding/first_stims_offset.json"


def shift_tier(tier: Tier, offset: float) -> Tier:
    """Return a copy of ``tier`` with every interval shifted by ``offset`` seconds (label/duration
    preserved)."""
    return Tier(
        tier.name,
        [Interval(iv.start + offset, iv.end + offset, iv.label) for iv in tier.intervals],
    )


def apply_first_stims_offset(
    results_dir: Path | str, offset: float, *, reason: str = "spectrogram_frame_center"
) -> dict:
    """Back up and shift a subject's ``first_stims.txt`` onsets by ``offset`` seconds.

    Idempotent: if the marker already exists the file is left untouched. Returns a status dict
    (``status`` ∈ ``applied`` / ``already_applied`` / ``no_first_stims``).
    """
    rd = Path(results_dir)
    fs_path = rd / FIRST_STIMS
    marker = rd / MARKER_REL
    if marker.exists():
        prev = json.loads(marker.read_text(encoding="utf-8"))
        return {"subject": rd.name, "status": "already_applied", "offset": prev.get("offset_s")}
    if not fs_path.exists():
        return {"subject": rd.name, "status": "no_first_stims"}

    tier = read_tier(fs_path, "first_stims")
    backup = rd / BACKUP_NAME
    if not backup.exists():  # never clobber an existing (original) backup
        shutil.copy2(fs_path, backup)
    write_tier(shift_tier(tier, offset), fs_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {"offset_s": offset, "reason": reason, "n_intervals": len(tier.intervals)}, indent=2
        ),
        encoding="utf-8",
    )
    return {
        "subject": rd.name,
        "status": "applied",
        "offset": offset,
        "n": len(tier.intervals),
        "backup": str(backup),
    }


def restore_first_stims(results_dir: Path | str) -> dict:
    """Undo :func:`apply_first_stims_offset` by restoring ``first_stims.txt`` from the backup."""
    rd = Path(results_dir)
    backup = rd / BACKUP_NAME
    if not backup.exists():
        return {"subject": rd.name, "status": "no_backup"}
    shutil.copy2(backup, rd / FIRST_STIMS)
    marker = rd / MARKER_REL
    if marker.exists():
        marker.unlink()
    return {"subject": rd.name, "status": "restored"}
