"""Tests for the first_stims offset correction (backup + idempotent shift + restore)."""

from __future__ import annotations

import json

from rpcoding.core.first_stims_offset import (
    BACKUP_NAME,
    FIRST_STIMS,
    MARKER_REL,
    apply_first_stims_offset,
    restore_first_stims,
    shift_tier,
)
from rpcoding.core.labels import Interval, Tier, read_tier, write_tier


def test_shift_tier_preserves_label_and_duration():
    t = Tier("first_stims", [Interval(1.0, 2.0, "a"), Interval(10.0, 10.5, "b")])
    s = shift_tier(t, 0.0174)
    assert [(round(i.start, 4), round(i.end, 4), i.label) for i in s.intervals] == [
        (1.0174, 2.0174, "a"),
        (10.0174, 10.5174, "b"),
    ]


def _write_first_stims(rd, onsets):
    rd.mkdir(parents=True, exist_ok=True)
    write_tier(
        Tier("first_stims", [Interval(o, o + 1.0, str(i)) for i, o in enumerate(onsets)]),
        rd / FIRST_STIMS,
    )


def test_apply_backs_up_shifts_and_marks(tmp_path):
    rd = tmp_path / "D90"
    _write_first_stims(rd, [0.0, 540.0, 1080.0, 1620.0])
    res = apply_first_stims_offset(rd, 0.0174)
    assert res["status"] == "applied" and res["n"] == 4
    # the live file is shifted
    starts = [round(iv.start, 4) for iv in read_tier(rd / FIRST_STIMS)]
    assert starts == [0.0174, 540.0174, 1080.0174, 1620.0174]
    # the backup holds the originals
    bak = [round(iv.start, 4) for iv in read_tier(rd / BACKUP_NAME)]
    assert bak == [0.0, 540.0, 1080.0, 1620.0]
    # the marker records the offset
    marker = json.loads((rd / MARKER_REL).read_text(encoding="utf-8"))
    assert marker["offset_s"] == 0.0174 and marker["n_intervals"] == 4


def test_apply_is_idempotent(tmp_path):
    rd = tmp_path / "D86"
    _write_first_stims(rd, [0.0, 540.0])
    apply_first_stims_offset(rd, 0.0174)
    res2 = apply_first_stims_offset(rd, 0.0174)  # second call must not shift again
    assert res2["status"] == "already_applied"
    starts = [round(iv.start, 4) for iv in read_tier(rd / FIRST_STIMS)]
    assert starts == [0.0174, 540.0174]  # not doubled


def test_restore_undoes_the_shift(tmp_path):
    rd = tmp_path / "D42"
    _write_first_stims(rd, [1.0, 2.0])
    apply_first_stims_offset(rd, 0.0174)
    out = restore_first_stims(rd)
    assert out["status"] == "restored"
    assert [round(iv.start, 4) for iv in read_tier(rd / FIRST_STIMS)] == [1.0, 2.0]
    assert not (rd / MARKER_REL).exists()  # marker cleared -> re-appliable
    # and a subsequent apply works again from the restored original
    assert apply_first_stims_offset(rd, 0.0174)["status"] == "applied"


def test_apply_no_first_stims(tmp_path):
    rd = tmp_path / "D99"
    rd.mkdir()
    assert apply_first_stims_offset(rd, 0.0174)["status"] == "no_first_stims"
