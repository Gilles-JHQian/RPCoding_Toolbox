r"""Merge a multi-part recording's numbered ``.mat`` files into single files (in D_Data).

Some subjects are recorded in more than one part, so ``ecog_preprocessing.m`` writes
``Trials1.mat`` / ``Trials2.mat`` and ``trialInfo1.mat`` / ``trialInfo2.mat`` (under
``<subject>/<date>/mat/``) plus ``experiment1.mat`` / ``experiment2.mat`` (under ``<subject>/mat/``)
and never a plain ``Trials.mat`` — so the response-coding pipeline (which needs exactly one
``Trials.mat``) can't run. This merges them, matching the lab's ``combine_trialInfo.m`` convention:

- **Trials / trialInfo**: the parts are concatenated in order (part 1 then part 2 …), à la
  ``horzcat`` — trial numbers and each part's timestamps are left untouched (no renumbering).
- **experiment**: the parts are content-identical (same electrodes/metadata), so the first is kept.

Each merged file is written next to its parts; an existing merged file is never clobbered.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import scipy.io as sio

_PART_RE = re.compile(r"^(?P<base>[A-Za-z_]+?)(?P<num>\d+)\.mat$", re.IGNORECASE)


@dataclass
class MergeResult:
    """Outcome for one merged output file."""

    name: str  # output filename, e.g. "Trials.mat"
    directory: str
    status: str  # merged | exists | single_part | no_parts
    n_parts: int
    detail: str = ""


def numbered_parts(directory: Path | str, base: str) -> list[Path]:
    """Sorted ``[base1.mat, base2.mat, …]`` in ``directory`` (exact base, numeric suffix)."""
    found: list[tuple[int, Path]] = []
    for p in Path(directory).glob("*.mat"):
        m = _PART_RE.match(p.name)
        if m and m.group("base").lower() == base.lower():
            found.append((int(m.group("num")), p))
    return [p for _, p in sorted(found)]


def _load_var(path: Path, var: str) -> np.ndarray:
    raw = sio.loadmat(str(path))  # format-preserving (no simplify_cells)
    if var not in raw:
        have = [k for k in raw if not k.startswith("__")]
        raise KeyError(f"{path.name}: variable '{var}' not found (have {have})")
    return np.atleast_2d(raw[var])


def _merge(directory: Path | str, base: str, var: str, *, concat: bool) -> MergeResult:
    directory = Path(directory)
    out = directory / f"{base}.mat"
    parts = numbered_parts(directory, base)
    if not parts:
        return MergeResult(out.name, str(directory), "no_parts", 0)
    if len(parts) == 1:
        return MergeResult(out.name, str(directory), "single_part", 1, f"only {parts[0].name}")
    if out.exists():
        return MergeResult(out.name, str(directory), "exists", len(parts), "kept existing file")
    if concat:
        # Trials (struct array) / trialInfo (cell array): concatenate 1xN parts along trial axis.
        try:
            combined = np.concatenate([_load_var(p, var) for p in parts], axis=1)
        except (TypeError, ValueError) as exc:  # mismatched struct fields across parts
            raise ValueError(f"cannot concatenate {base} parts (differing fields?): {exc}") from exc
        sio.savemat(str(out), {var: combined})
        n = combined.shape[1]
        detail = f"{n} rows from {', '.join(p.name for p in parts)}"
    else:
        # experiment: parts are content-identical -> copy the first. (Copying also dodges scipy's
        # 31-char field-name limit, which MATLAB-written structs like experiment can exceed, e.g.
        # 'nspike_num_channels_to_write_high'.)
        shutil.copy2(parts[0], out)
        detail = f"copied {parts[0].name} ({len(parts)} identical parts)"
    return MergeResult(out.name, str(directory), "merged", len(parts), detail)


def merge_subject(d_data_subject_dir: Path | str) -> list[MergeResult]:
    """Merge a subject's numbered files: Trials/trialInfo (``<date>/mat/``) + experiment (``mat/``).

    Returns one :class:`MergeResult` per output. A subject with no numbered parts yields all
    ``no_parts`` (nothing written) — safe to run on any subject.
    """
    base = Path(d_data_subject_dir)
    results: list[MergeResult] = []
    # Trials + trialInfo live under each <date>/mat/ dir that holds their numbered parts.
    date_mat_dirs = sorted(
        {p.parent for p in base.glob("*/mat/Trials*.mat")}
        | {p.parent for p in base.glob("*/mat/trialInfo*.mat")}
    )
    for d in date_mat_dirs:
        results.append(_merge(d, "Trials", "Trials", concat=True))
        results.append(_merge(d, "trialInfo", "trialInfo", concat=True))
    # experiment lives under <subject>/mat/.
    results.append(_merge(base / "mat", "experiment", "experiment", concat=False))
    return results
