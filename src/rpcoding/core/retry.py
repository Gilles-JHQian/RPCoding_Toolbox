"""Retry transient cloud-storage IO errors (Box/OneDrive sync hiccups).

Box (and other cloud drives) intermittently fail a read/write *mid-sync* with an ``OSError`` such as
WinError 1006 ("the volume for a file has been changed; the file specified is no longer valid") or a
short-lived lock (``PermissionError``). These clear on their own within a second, so a brief wait +
retry almost always succeeds. A genuinely missing file (``FileNotFoundError``) is *not* transient
and is never retried.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

_log = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_ATTEMPTS = 4
TRANSIENT_DELAY = 0.6  # seconds between attempts


def is_transient_io_error(exc: BaseException) -> bool:
    """True for a cloud-sync hiccup worth retrying; False for a genuinely missing file."""
    if isinstance(exc, FileNotFoundError):
        return False
    return isinstance(exc, OSError)


def retry_transient_io(
    fn: Callable[[], T],
    *,
    attempts: int = TRANSIENT_ATTEMPTS,
    delay: float = TRANSIENT_DELAY,
    on_retry: Callable[[int, OSError], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn``; on a transient cloud-IO ``OSError``, wait then retry up to ``attempts`` times.

    Re-raises immediately for non-transient errors (e.g. ``FileNotFoundError``) and after the final
    attempt. ``on_retry(attempt, exc)`` fires before each wait (e.g. to surface "retrying…" in the
    UI); ``sleep`` is injectable so tests don't actually wait.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except OSError as exc:
            if not is_transient_io_error(exc) or attempt >= attempts:
                raise
            _log.warning("Transient IO error (attempt %d/%d): %s", attempt, attempts, exc)
            if on_retry is not None:
                on_retry(attempt, exc)
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
