r"""Resolve / auto-combine ``Trials.mat`` for multi-session subjects.

A subject recorded across two EDF sessions has per-session ``Trials1.mat`` / ``Trials2.mat`` under
``D_Data/<task>/<subj>/<date>/mat/`` (the variable *inside* each is always ``Trials``, not
``Trials<N>``). The lab has no script for this — it was hand-combined per subject, inconsistently
(some files renumber the ``Trial`` field 1..N, some keep each part's original numbering). We
standardize on **renumbering to a continuous 1..N**, matching the most recent same-task hand-combine
(D134, NoDelay) so downstream code can treat ``Trial`` as a unique index.

Resolution policy (see memory: multi-session-support):
  * An existing combined ``Trials.mat`` (single session, or a hand-made combine) is used as-is.
  * Otherwise, if ≥2 per-session ``Trials<N>.mat`` exist, they are combined and written back into
    **D_Data**, next to the per-session files (``<date>/mat/Trials.mat``) — the lab's own layout, so
    downstream steps enrich it in place (like a single-session subject).
  * A lone ``Trials1.mat`` (suffixed but single) is used directly.

The walk tolerates Box cloud-placeholder ``OSError``s (which crash ``pathlib.glob``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.matio import load_trials
from rpcoding.core.rpcode.rpcode2trials import save_trials

COMBINED_NAME = "Trials.mat"
_SESSION_RE = re.compile(r"^Trials(\d+)\.mat$", re.IGNORECASE)


@dataclass
class ResolvedTrials:
    """Outcome of resolving a subject's ``Trials.mat`` (multi-session aware)."""

    path: Path  # the Trials.mat downstream steps should read/enrich
    auto_combined: bool  # True iff this module built it from per-session files
    sessions: list[Path] = field(default_factory=list)  # per-session Trials<N> found
    n_trials: int | None = None

    @property
    def multi_session(self) -> bool:
        return len(self.sessions) >= 2


def _scan_trials_mats(base: Path) -> tuple[list[Path], list[tuple[int, Path]]]:
    """Walk ``base`` for ``**/mat/Trials*.mat`` -> (combined ``Trials.mat`` list, per-session list).

    Tolerant of cloud-placeholder ``OSError``s. Per-session results are sorted by suffix number.
    """
    combined: list[Path] = []
    sessions: list[tuple[int, Path]] = []
    for root, _dirs, files in os.walk(base, onerror=lambda _e: None):
        if Path(root).name.lower() != "mat":
            continue
        for f in files:
            if f.lower() == "trials.mat":
                combined.append(Path(root) / f)
                continue
            m = _SESSION_RE.match(f)
            if m:
                sessions.append((int(m.group(1)), Path(root) / f))
    sessions.sort(key=lambda np_: (np_[0], str(np_[1])))
    return combined, sessions


def combine_session_trials(trials_lists: list[list[dict]]) -> list[dict]:
    """Concatenate per-session Trials in order, renumbering ``Trial`` to a continuous 1..N.

    This is the only transform the lab's manual combine applies — everything else (``Auditory``,
    ``Start``, codes) is plain concatenation.
    """
    combined: list[dict] = []
    n = 0
    for trials in trials_lists:
        for tr in trials:
            n += 1
            t = dict(tr)
            if "Trial" in t:  # preserve the field's numeric type (MATLAB double vs int)
                t["Trial"] = type(t["Trial"])(n)
            else:
                t["Trial"] = n
            combined.append(t)
    return combined


def resolve_trials_mat(d_data_subject_dir: Path | str, results_dir: Path | str) -> ResolvedTrials:
    """Locate the ``Trials.mat`` to use, auto-combining per-session files when needed.

    Raises ``FileNotFoundError`` if neither a combined nor per-session Trials file exists, and
    ``ValueError`` if two recording dates each carry a combined ``Trials.mat`` (ambiguous).
    """
    base = Path(d_data_subject_dir)
    combined, sessions = _scan_trials_mats(base)
    session_paths = [p for _n, p in sessions]

    # A corrected Trials.mat in the results dir wins over D_Data: the trigger-fix gadget writes its
    # correction there (never onto the shared raw), so downstream reads the corrected one. The
    # D_Data scan still runs so multi-session status is reported. A plain subject has no
    # results/Trials.mat, so normal resolution is unaffected. (The auto-combine below writes to
    # D_Data, not here.)
    override = Path(results_dir) / COMBINED_NAME
    if override.exists() and not any(override.samefile(p) for p in combined if p.exists()):
        return ResolvedTrials(path=override, auto_combined=False, sessions=session_paths)

    if combined:
        # Prefer the canonical <date>/mat/Trials.mat; a stray copy elsewhere is ignored.
        canonical = [p for p in combined if paths._is_canonical_trials(p, base)]
        pool = canonical or sorted(combined)
        if len(pool) > 1:
            raise ValueError(
                f"More than one combined Trials.mat under {base}: {pool}. "
                "Expected exactly one canonical <date>/mat/Trials.mat."
            )
        return ResolvedTrials(path=pool[0], auto_combined=False, sessions=session_paths)

    if len(sessions) >= 2:
        merged = combine_session_trials([load_trials(p) for p in session_paths])
        # Write the combined file back into D_Data, alongside the last session's per-part files
        # (canonical <date>/mat/Trials.mat) — the lab's own layout, so a re-resolve finds it as the
        # existing combined and downstream enriches it in place.
        out = session_paths[-1].with_name(COMBINED_NAME)
        save_trials(out, merged)
        return ResolvedTrials(
            path=out, auto_combined=True, sessions=session_paths, n_trials=len(merged)
        )

    if len(sessions) == 1:
        return ResolvedTrials(path=session_paths[0], auto_combined=False, sessions=session_paths)

    raise FileNotFoundError(
        f"No Trials.mat or per-session Trials<N>.mat under {base} (**/mat/Trials*.mat)"
    )
