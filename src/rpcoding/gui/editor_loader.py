"""Map a manual pipeline step to the editor tiers it loads and the file ``save`` writes.

Both manual steps (mark-first-stimuli, response-coding) share one unified lane layout — first stim,
condition, cue, response — so the two editors look the same; only which lane is editable (and where
``save`` writes) differs by step. Reference tiers load read-only; the response lane starts from the
saved coding, else the MFA-aligned response words, else empty.
"""

from __future__ import annotations

from pathlib import Path

from rpcoding.core import paths
from rpcoding.core.events.block_onsets import load_block_onsets_tier
from rpcoding.core.labels import Tier, read_tier
from rpcoding.core.mfa.ingest import ingest_mfa_tiers
from rpcoding.core.steps import Step

TierSpec = tuple[str, Tier, bool]


def _load_or_empty(path: Path, name: str) -> Tier:
    """Read a tier file if present, else an empty tier (so a fresh edit starts blank)."""
    return read_tier(path, name) if path.exists() else Tier(name, [])


def _response_tier(results_dir: Path) -> Tier:
    """The response lane: the saved coding if present, else the MFA response words, else empty."""
    saved = results_dir / paths.RESP_WORDS_ERRORS_TXT
    if saved.exists():
        return read_tier(saved, "response")
    mfa = ingest_mfa_tiers(results_dir / paths.MFA_DIRNAME)
    src = mfa.get("mfa_resp_words")
    return Tier("response", list(src.intervals)) if src is not None else Tier("response", [])


def tiers_for_step(results_dir: Path | str, step: Step) -> tuple[list[TierSpec], Path | None]:
    """Return ``(tier_specs, save_path)`` for an editor-backed step (save_path None for denoise).

    Raises ``ValueError`` for steps that aren't edited in the audio editor.
    """
    results_dir = Path(results_dir)
    is_first = step == Step.MARK_FIRST_STIMS
    is_resp = step == Step.RESPONSE_CODING
    is_denoise = step == Step.DENOISE
    if not (is_first or is_resp or is_denoise):
        raise ValueError(f"{step} is not an editor-backed step")

    # Top, read-only: a marker per block onset in allblocks.wav, so you can jump to a block before
    # marking its first stimulus (derived from block_wav_onsets.mat; empty if not concatenated yet).
    blocks = load_block_onsets_tier(results_dir)
    first = _load_or_empty(results_dir / paths.FIRST_STIMS_TXT, "first_stims")
    cond = _load_or_empty(results_dir / paths.CONDITION_EVENTS_TXT, "condition_events")
    cue = _load_or_empty(results_dir / paths.CUE_EVENTS_TXT, "cue_events")
    if is_denoise:
        # Denoise edits the audio, not labels: show the reference tiers read-only, nothing editable
        # and no label save target (it completes via the audio write, not a tier save).
        denoise_specs: list[TierSpec] = [
            ("block_onsets", blocks, False),
            ("first_stims", first, False),
            ("condition_events", cond, False),
            ("cue_events", cue, False),
        ]
        return denoise_specs, None
    specs: list[TierSpec] = [
        ("block_onsets", blocks, False),
        ("first_stims", first, is_first),
        ("condition_events", cond, False),
        ("cue_events", cue, False),
        ("response", _response_tier(results_dir), is_resp),
    ]
    save_path = results_dir / (paths.FIRST_STIMS_TXT if is_first else paths.RESP_WORDS_ERRORS_TXT)
    return specs, save_path
