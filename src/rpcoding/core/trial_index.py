"""Map a time to its trial, from the cue/condition event tiers (for the Trial Info panel).

Cue labels are ``<trial>_<sound>`` and condition labels are ``<trial>_<task>``
(Yes/No / Repeat / :=:); they are joined on the trial index. Pure (no Qt), testable headless.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from rpcoding.core.labels import Tier


@dataclass(frozen=True)
class TrialInfo:
    trial: int
    start: float  # cue onset (seconds)
    end: float  # cue offset (seconds)
    task: str | None  # from condition events (Yes/No / Repeat / :=:)
    stim: str | None  # sound filename from the cue label


def parse_trial_label(label: str) -> tuple[int | None, str]:
    """Split ``<trial>_<rest>`` -> (trial_index, rest); (None, label) if no leading integer."""
    head, _, rest = label.partition("_")
    try:
        return int(head), rest
    except ValueError:
        return None, label


class TrialIndex:
    def __init__(self, cue_tier: Tier, condition_tier: Tier | None = None):
        cond_by_trial: dict[int, str] = {}
        if condition_tier is not None:
            for iv in condition_tier:
                idx, task = parse_trial_label(iv.label)
                if idx is not None:
                    cond_by_trial[idx] = task
        infos: list[TrialInfo] = []
        for iv in cue_tier:
            idx, stim = parse_trial_label(iv.label)
            if idx is None:
                continue
            infos.append(TrialInfo(idx, iv.start, iv.end, cond_by_trial.get(idx), stim))
        infos.sort(key=lambda t: t.start)
        self._infos = infos
        self._starts = [t.start for t in infos]

    def __len__(self) -> int:
        return len(self._infos)

    def at(self, t: float) -> TrialInfo | None:
        """The trial whose cue onset is the latest at/<= ``t`` (None before the first trial)."""
        if not self._infos:
            return None
        i = bisect_right(self._starts, t) - 1
        return self._infos[i] if i >= 0 else None
