"""Tests for Audacity tier (label-track) I/O."""

from __future__ import annotations

from rpcoding.core.labels import (
    Interval,
    Tier,
    format_tier,
    parse_tier,
    read_tier,
    write_tier,
)


def test_roundtrip_special_chars_and_empty_label():
    tier = Tier(
        "condition_events",
        [
            Interval(2.171481, 2.671481, "1_:=:"),
            Interval(8.305016, 8.805016, "2_Yes/No"),
            Interval(0.0, 0.5, ""),
        ],
    )
    parsed = parse_tier(format_tier(tier), "condition_events")
    assert parsed.intervals == tier.intervals


def test_format_precision_matches_matlab():
    tier = Tier("t", [Interval(4.314335, 4.961834, "1")])
    assert format_tier(tier) == "4.314335\t4.961834\t1\n"


def test_read_first_stims_fixture(fixtures_dir):
    p = fixtures_dir / "label_samples" / "first_stims.txt"
    tier = read_tier(p)
    assert [iv.label for iv in tier] == ["1", "2", "3", "4"]
    assert tier.intervals[0].start == 4.314335
    # byte round-trip (newline-agnostic read vs LF format)
    assert format_tier(tier) == p.read_text(encoding="utf-8")


def test_write_then_read(tmp_path):
    tier = Tier("t", [Interval(1.0, 2.0, "a"), Interval(2.5, 3.0, "b b")])
    p = tmp_path / "out.txt"
    write_tier(tier, p)
    assert read_tier(p, "t").intervals == tier.intervals


def test_malformed_line_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_tier("only_one_field\n")
