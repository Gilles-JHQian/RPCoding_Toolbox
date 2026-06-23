"""Parse MFA output label files (mfa/mfa_*.txt) into Tier objects."""

from __future__ import annotations

from pathlib import Path

from rpcoding.core.labels import Tier, read_tier

# Output tiers the pipeline may produce (yes/no for Delay; whisper/manual added after review).
MFA_TIER_NAMES = (
    "mfa_stim_words",
    "mfa_stim_phones",
    "mfa_resp_words",
    "mfa_resp_phones",
    "mfa_yes_words",
    "mfa_yes_phones",
    "mfa_no_words",
    "mfa_no_phones",
    "mfa_whisper_rscode",
    "mfa_words",
    "mfa_phones",
    "mfa_manual_errcode",
)


def ingest_mfa_tiers(mfa_dir: Path | str) -> dict[str, Tier]:
    """Read whichever ``mfa_*.txt`` tiers exist in ``mfa_dir`` into a name -> Tier dict."""
    mfa_dir = Path(mfa_dir)
    tiers: dict[str, Tier] = {}
    for name in MFA_TIER_NAMES:
        path = mfa_dir / f"{name}.txt"
        if path.exists():
            tiers[name] = read_tier(path, name)
    return tiers
