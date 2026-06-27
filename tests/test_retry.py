"""Tests for transient cloud-IO retry."""

from __future__ import annotations

import pytest

from rpcoding.core.retry import is_transient_io_error, retry_transient_io


def test_succeeds_first_try():
    assert retry_transient_io(lambda: 42, sleep=lambda _d: None) == 42


def test_retries_then_succeeds():
    calls = {"n": 0}
    waits: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError(1006, "the volume for a file has been changed")
        return "ok"

    out = retry_transient_io(flaky, delay=0.6, sleep=waits.append)
    assert out == "ok"
    assert calls["n"] == 3
    assert waits == [0.6, 0.6]  # waited before each of the 2 retries


def test_file_not_found_is_not_retried():
    calls = {"n": 0}

    def missing():
        calls["n"] += 1
        raise FileNotFoundError("no such file")

    with pytest.raises(FileNotFoundError):
        retry_transient_io(missing, sleep=lambda _d: None)
    assert calls["n"] == 1  # never retried


def test_reraises_after_exhausting_attempts():
    calls = {"n": 0}

    def always():
        calls["n"] += 1
        raise OSError(1006, "volume changed")

    with pytest.raises(OSError):
        retry_transient_io(always, attempts=3, sleep=lambda _d: None)
    assert calls["n"] == 3


def test_on_retry_callback_fires_per_retry():
    seen: list[int] = []
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("transient")
        return 1

    retry_transient_io(
        flaky,
        on_retry=lambda attempt, _exc: seen.append(attempt),
        sleep=lambda _d: None,
    )
    assert seen == [1, 2]


def test_is_transient_classification():
    assert is_transient_io_error(OSError(1006, "volume changed"))
    assert is_transient_io_error(PermissionError("locked"))
    assert not is_transient_io_error(FileNotFoundError("missing"))
    assert not is_transient_io_error(ValueError("not io"))
