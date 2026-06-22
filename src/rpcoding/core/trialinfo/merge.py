"""Pure helpers ported from combine_trialInfo.m, fix_trialInfo_blocks.m, cell2mat_trials.m.

These operate on the canonical "list of per-trial dicts" representation (see core.matio).
"""

from __future__ import annotations

import math

from rpcoding.core.matio import trial_block


def block_sequence(trials: list[dict]) -> list[int]:
    """Distinct block numbers in order of appearance (e.g. [1, 2, 3, 4] or [3, 4])."""
    seq: list[int] = []
    for t in trials:
        b = int(round(float(trial_block(t))))
        if not seq or seq[-1] != b:
            seq.append(b)
    return seq


def combine_trialinfos(lists: list[list[dict]]) -> list[dict]:
    """Concatenate multiple trial lists into one (horzcat in combine_trialInfo.m)."""
    combined: list[dict] = []
    for lst in lists:
        combined.extend(lst)
    return combined


def homogenize_trials(trials: list[dict]) -> list[dict]:
    """Port of cell2mat_trials.m: uniform fields, '' for char / NaN for numeric, fields sorted."""
    all_fields: list[str] = []
    for t in trials:
        for k in t:
            if k not in all_fields:
                all_fields.append(k)
    defaults: dict[str, object] = {}
    for f in all_fields:
        for t in trials:
            if f in t:
                defaults[f] = "" if isinstance(t[f], str) else math.nan
                break
    ordered = sorted(all_fields)
    return [{f: t.get(f, defaults[f]) for f in ordered} for t in trials]


def fix_trialinfo_blocks(trials: list[dict], blocks: list[int]) -> list[dict]:
    """Port of fix_trialInfo_blocks.m: relabel block numbers, drop extra/incomplete trials.

    Walks the trials; each time the block field changes, advances to the next target block in
    ``blocks``. Once more blocks appear than ``blocks`` provides, truncates the remaining trials.
    """
    if not trials:
        return []
    out = [dict(t) for t in trials]
    b = 0
    curb = int(round(float(trial_block(out[0]))))
    tidx = len(out)
    for i, t in enumerate(out):
        blk = int(round(float(trial_block(t))))
        if blk != curb:
            b += 1
            curb = blk
        if b > len(blocks) - 1:
            tidx = i
            break
        t["block"] = blocks[b]
    return out[:tidx]
