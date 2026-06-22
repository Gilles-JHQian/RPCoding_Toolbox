"""Word / nonword classification from the lab's ``word_lst.mat`` / ``nonword_lst.mat``.

These ``.mat`` files store a cell array of stimulus filenames (e.g. ``casef.wav``). Classification
is an exact filename match, mirroring the MATLAB ``any(strcmp(cue_word, words))`` check.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rpcoding.core.matio import load_mat

WORD = "Word"
NONWORD = "Nonword"


def _flatten(value) -> list:
    if isinstance(value, str):
        return [value]
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        out: list = []
        for v in value:
            out.extend(_flatten(v))
        return out
    return [value]


def load_name_list(path: Path | str, var: str) -> list[str]:
    """Load a cell array of stimulus filenames stored under ``var`` in a ``.mat`` file."""
    raw = load_mat(path)
    if var not in raw:
        raise KeyError(f"{path}: variable {var!r} not found (have {list(raw)})")
    return [str(x) for x in _flatten(raw[var])]


def classify(stim: str, words: set[str], nonwords: set[str]) -> str | None:
    """Return ``'Word'`` / ``'Nonword'`` / ``None`` for a stimulus filename."""
    if stim in words:
        return WORD
    if stim in nonwords:
        return NONWORD
    return None
