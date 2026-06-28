"""Discover per-block TrialData.mat files and combine them into one trialInfo.

Each ``D###_Block_N_TrialData.mat`` holds ``trialInfo`` (a cell of trial structs) that is cumulative
*within its acquisition run*, not globally. A subject run in two sessions yields e.g. Block_2 ->
blocks [1, 2] and Block_4 -> blocks [3, 4]; the "highest block" file alone is then incomplete (the
D140 case). :func:`build_trialinfo` chains the cumulative run-end files to cover blocks 1..N.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rpcoding.core.matio import load_trialinfo, save_mat
from rpcoding.core.trialinfo.merge import block_sequence, combine_trialinfos

_TRIALDATA_RE = re.compile(r"_Block_(\d+)_TrialData\.mat$", re.IGNORECASE)


class IncompleteTrialInfoError(RuntimeError):
    """Raised when the TrialData files cannot be combined to cover blocks 1..N."""


@dataclass
class TrialDataFile:
    """One discovered TrialData.mat with its trials and the block numbers they span."""

    path: Path
    block_num: int  # from filename
    trials: list[dict]
    blocks: list[int]  # distinct block-field values, in order

    @property
    def min_block(self) -> int:
        return self.blocks[0]

    @property
    def max_block(self) -> int:
        return self.blocks[-1]


def discover_trialdata_files(
    all_blocks_dir: Path | str | Iterable[Path | str],
) -> list[TrialDataFile]:
    """Load every ``*_Block_N_TrialData.mat`` (Practice excluded) from one dir or several.

    Pass an iterable of dirs for a multi-session subject whose blocks are split across session
    folders; the files are aggregated (and :func:`select_and_combine` resolves any block that
    appears in more than one session).
    """
    if isinstance(all_blocks_dir, (str, Path)):
        dirs: list[Path] = [Path(all_blocks_dir)]
    else:
        dirs = [Path(d) for d in all_blocks_dir]
    files: list[TrialDataFile] = []
    for d in dirs:
        for p in sorted(d.glob("*_TrialData.mat")):
            if "pract" in p.name.lower():  # 'Practice' or 'Pract'
                continue
            m = _TRIALDATA_RE.search(p.name)
            if not m:
                continue
            trials = load_trialinfo(p)
            files.append(
                TrialDataFile(
                    path=p,
                    block_num=int(m.group(1)),
                    trials=trials,
                    blocks=block_sequence(trials),
                )
            )
    return files


def select_and_combine(files: list[TrialDataFile]) -> tuple[list[dict], dict]:
    """Chain cumulative run-end files to cover blocks 1..max exactly; returns (trials, info)."""
    if not files:
        raise IncompleteTrialInfoError("No TrialData files found")
    target_max = max(f.max_block for f in files)

    selected: list[TrialDataFile] = []
    need = target_max
    while need >= 1:
        candidates = [f for f in files if f.max_block == need]
        if not candidates:
            raise IncompleteTrialInfoError(
                f"No TrialData file ends at block {need}; cannot cover blocks 1..{target_max}"
            )
        # Widest coverage first (smallest min_block); on a cross-session tie pick the most-complete
        # run, then the latest session folder. So a block half-aborted in one session loses to its
        # full re-run in another (the user's "most complete / last" rule).
        widest = min(f.min_block for f in candidates)
        tied = [f for f in candidates if f.min_block == widest]
        chosen = max(tied, key=lambda f: (len(f.trials), str(f.path)))
        selected.append(chosen)
        need = chosen.min_block - 1
    selected.reverse()

    combined = combine_trialinfos([f.trials for f in selected])
    seq = block_sequence(combined)
    if seq != list(range(1, target_max + 1)):
        raise IncompleteTrialInfoError(
            f"Combined block sequence {seq} is not contiguous 1..{target_max}"
        )

    session_dirs = {str(f.path.parent) for f in selected}
    info = {
        "target_max_block": target_max,
        "total_trials": len(combined),
        "combined_from_single_file": len(selected) == 1,
        "n_session_dirs": len(session_dirs),
        "multi_session": len(session_dirs) > 1,
        "selected_files": [
            {"file": f.path.name, "blocks": f.blocks, "n_trials": len(f.trials)} for f in selected
        ],
    }
    return combined, info


def save_trialinfo(path: Path | str, trials: list[dict]) -> None:
    """Write trials as ``trialInfo.mat`` (variable ``trialInfo``, a cell array of structs)."""
    arr = np.empty((1, len(trials)), dtype=object)
    for i, t in enumerate(trials):
        arr[0, i] = t
    save_mat(path, {"trialInfo": arr})


def build_trialinfo(
    all_blocks_dir: Path | str | Iterable[Path | str],
    out_mat: Path | str,
    provenance_path: Path | str | None = None,
) -> dict:
    """Discover, combine, and write trialInfo.mat (+ optional provenance json). Returns the info.

    ``all_blocks_dir`` may be a single dir or several (a multi-session subject); see
    :func:`discover_trialdata_files`.
    """
    files = discover_trialdata_files(all_blocks_dir)
    if not files:
        raise FileNotFoundError(f"No *_TrialData.mat files in {all_blocks_dir}")
    combined, info = select_and_combine(files)
    save_trialinfo(out_mat, combined)
    if provenance_path is not None:
        Path(provenance_path).write_text(json.dumps(info, indent=2), encoding="utf-8", newline="\n")
    return info
