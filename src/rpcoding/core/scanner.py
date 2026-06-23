"""Discover subjects (D<number> / S<number>, optional trailing letters) under a task folder."""

from __future__ import annotations

import re
from pathlib import Path

_SUBJECT_RE = re.compile(r"^([DS])(\d+)([A-Za-z]*)$")


def _sort_key(name: str):
    m = _SUBJECT_RE.match(name)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (name, 0, "")


def scan_subjects(d_data_task_dir: Path | str) -> list[str]:
    """Return sorted subject ids from subfolders matching D<n>/S<n> (e.g. D24, S3, D107B)."""
    d = Path(d_data_task_dir)
    if not d.is_dir():
        return []
    subs = [p.name for p in d.iterdir() if p.is_dir() and _SUBJECT_RE.match(p.name)]
    return sorted(subs, key=_sort_key)
