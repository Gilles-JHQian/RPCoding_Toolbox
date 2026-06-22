r"""Audacity-compatible label-track ("tier") I/O.

Format: one interval per line, ``start<TAB>end<TAB>label`` with times in seconds. This matches
Audacity's exported label tracks and the lab's MATLAB ``fprintf('%f\t%f\t%s\n', ...)`` output
(6 decimal places), so files stay interoperable with the existing pipeline. Labels may contain
arbitrary characters except TAB/newline (e.g. ``1_:=:``, ``2_Yes/No``).

Output is always written with LF newlines for cross-platform determinism; reading is
newline-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PRECISION = 6


@dataclass
class Interval:
    """A labeled time span, in seconds."""

    start: float
    end: float
    label: str = ""


@dataclass
class Tier:
    """A named track of intervals (one Audacity label track)."""

    name: str
    intervals: list[Interval] = field(default_factory=list)

    def __iter__(self):
        return iter(self.intervals)

    def __len__(self) -> int:
        return len(self.intervals)


def parse_tier(text: str, name: str = "") -> Tier:
    """Parse Audacity label-track text into a :class:`Tier`."""
    intervals: list[Interval] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            raise ValueError(f"Malformed label line (need >=2 tab fields): {raw!r}")
        start = float(parts[0])
        end = float(parts[1])
        label = parts[2] if len(parts) >= 3 else ""
        intervals.append(Interval(start, end, label))
    return Tier(name=name, intervals=intervals)


def read_tier(path: Path | str, name: str | None = None) -> Tier:
    """Read an Audacity label file into a :class:`Tier` (name defaults to the file stem)."""
    path = Path(path)
    if name is None:
        name = path.stem
    return parse_tier(path.read_text(encoding="utf-8"), name=name)


def format_tier(tier: Tier, precision: int = DEFAULT_PRECISION) -> str:
    """Render a tier as Audacity label-track text (one LF-terminated line per interval)."""
    return "".join(
        f"{iv.start:.{precision}f}\t{iv.end:.{precision}f}\t{iv.label}\n" for iv in tier.intervals
    )


def write_tier(tier: Tier, path: Path | str, precision: int = DEFAULT_PRECISION) -> None:
    """Write a tier to an Audacity-compatible label file (LF newlines)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_tier(tier, precision=precision), encoding="utf-8", newline="\n")
