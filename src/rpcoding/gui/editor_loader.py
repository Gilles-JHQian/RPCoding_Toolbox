"""Map a manual pipeline step to the editor tiers it loads and the file ``save`` writes.

Pure (no Qt): given a results dir and a manual :class:`Step`, return the list of
``(name, Tier, editable)`` tuples to feed :meth:`AudioEditor.set_tiers` plus the Audacity ``.txt``
path the editable tier saves to. Reference tiers (cue/condition events, MFA output) load read-only;
the one editable tier is what the coder produces.
"""

from __future__ import annotations

from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.labels import Tier, read_tier
from rpcoding.core.mfa.ingest import ingest_mfa_tiers
from rpcoding.core.steps import Step

# Reference (read-only) tiers shown during response coding, in display order.
_RESP_REFERENCE = (
    ("cue_events", paths.CUE_EVENTS_TXT),
    ("condition_events", paths.CONDITION_EVENTS_TXT),
)

TierSpec = tuple[str, Tier, bool]


def _load_or_empty(path: Path, name: str) -> Tier:
    """Read a tier file if present, else an empty tier (so a fresh edit starts blank)."""
    return read_tier(path, name) if path.exists() else Tier(name, [])


def tiers_for_step(results_dir: Path | str, step: Step) -> tuple[list[TierSpec], Path]:
    """Return ``(tier_specs, save_path)`` for a manual, editor-backed step.

    Raises ``ValueError`` for steps that aren't edited in the audio editor.
    """
    results_dir = Path(results_dir)

    if step == Step.MARK_FIRST_STIMS:
        save_path = results_dir / paths.FIRST_STIMS_TXT
        return [("first_stims", _load_or_empty(save_path, "first_stims"), True)], save_path

    if step == Step.RESPONSE_CODING:
        specs: list[TierSpec] = [
            (name, _load_or_empty(results_dir / fname, name), False)
            for name, fname in _RESP_REFERENCE
        ]
        for name, tier in ingest_mfa_tiers(results_dir / paths.MFA_DIRNAME).items():
            specs.append((name, tier, False))
        save_path = results_dir / paths.RESP_WORDS_ERRORS_TXT
        specs.append(("response", _load_or_empty(save_path, "response"), True))
        return specs, save_path

    raise ValueError(f"{step} is not an editor-backed manual step")
