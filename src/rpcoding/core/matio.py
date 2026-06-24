r"""MATLAB ``.mat`` I/O with normalization for the pipeline's heterogeneous trialInfo structures.

``scipy.io.loadmat(..., simplify_cells=True)`` collapses both the cell-of-structs and the
struct-array ``trialInfo`` layouts into a Python list of per-trial dicts, with char fields as
``str`` and numeric fields as ``float``. This module wraps that and adds the field-name "ladders"
the MATLAB scripts use (stim = ``sound|stim``, cue = ``cue|condition``, audio onset = one of five
names), mirroring their ``isfield`` checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import scipy.io as sio

# field-name ladders mirrored from the MATLAB isfield() checks
STIM_FIELDS = ("sound", "stim")
CUE_FIELDS = ("cue", "condition")
AUDIO_ONSET_FIELDS = (
    "audiostart",
    "audioStart",
    "stimulusAudioStart",
    "stimuliAlignedTrigger",
    "cueStart",
)


def load_mat(path: Path | str, *, simplify: bool = True) -> dict[str, Any]:
    """Load a ``.mat`` file. With ``simplify`` (default), cells/structs -> lists/dicts/str.

    Note: ``simplify`` also squeezes singleton dimensions, so a ``(1, N)`` numeric matrix comes
    back 1-D. Pass ``simplify=False`` when you need to preserve a numeric matrix's 2-D shape.
    """
    return sio.loadmat(str(path), simplify_cells=simplify)


def save_mat(path: Path | str, data: dict[str, Any]) -> None:
    """Write a dict of variables to a ``.mat`` file (creating parent dirs).

    ``do_compression=True`` matches MATLAB's default ``save`` (v7, zlib-compressed): without it
    scipy writes uncompressed .mat files that are ~20-40x larger than the MATLAB pipeline's.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sio.savemat(str(path), data, do_compression=True)


def _as_trial_list(value: Any) -> list[dict]:
    """Normalize a loaded ``trialInfo`` value into a list of per-trial dicts."""
    if isinstance(value, dict):  # single 1x1 struct -> one trial
        return [value]
    if isinstance(value, np.ndarray):
        value = value.tolist()
    return list(value)


def _load_record_list(path: Path | str, var: str) -> list[dict]:
    raw = load_mat(path)
    if var not in raw:
        raise KeyError(f"{path}: variable {var!r} not found (have {list(raw)})")
    return _as_trial_list(raw[var])


def load_trialinfo(path: Path | str, var: str = "trialInfo") -> list[dict]:
    """Load ``trialInfo`` as a list of per-trial dicts (cell- or struct-array agnostic)."""
    return _load_record_list(path, var)


def load_trials(path: Path | str, var: str = "Trials") -> list[dict]:
    """Load a ``Trials`` struct array as a list of per-trial dicts (has EDF ``.Auditory`` etc.)."""
    return _load_record_list(path, var)


# ---- field-ladder accessors (mirror MATLAB isfield checks) ----
def get_field(trial: dict, *names: str, default: Any = None) -> Any:
    """Return the first present field among ``names`` (mirrors MATLAB isfield ladders)."""
    for n in names:
        if n in trial:
            return trial[n]
    return default


def trial_stim(trial: dict) -> Any:
    """Stimulus identifier: ``sound`` else ``stim``."""
    return get_field(trial, *STIM_FIELDS)


def trial_cue(trial: dict) -> Any:
    """Condition/cue label: ``cue`` else ``condition``."""
    return get_field(trial, *CUE_FIELDS)


def trial_audio_onset(trial: dict) -> Any:
    """Audio onset time: first present of the five known field names."""
    return get_field(trial, *AUDIO_ONSET_FIELDS)


def trial_block(trial: dict) -> Any:
    """Block index (``block``)."""
    return trial.get("block")
