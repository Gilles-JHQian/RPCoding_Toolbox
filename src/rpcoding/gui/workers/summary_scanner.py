"""Compute per-subject status off the UI thread, in parallel, streaming results back.

The dashboard scan used to call ``SubjectSession(...).status()`` for every subject serially on the
GUI thread. Each call does ~15-20 ``stat()``/``exists()`` calls, and on a Box-synced folder a single
call can block 100-500 ms while a cloud placeholder is fetched — so a big scan froze low-CPU
machines. Moving it to a background thread keeps the UI responsive — that alone is the fix.

It runs **serially** (a single worker), NOT in parallel. Box's virtual filesystem serializes
concurrent placeholder access and locks up under load, so firing many ``stat()``s at once saturated
the Box driver and froze not just the app but every process touching the folder (the OS file
explorer included). The goal here is only to keep the UI thread free, not to scan faster, so one
worker is exactly right.

Each subject runs as a :class:`QRunnable`; results come back per subject via a queued signal so the
handler runs on the GUI thread (a ``QRunnable`` can't own signals, so each carries a tiny
:class:`QObject` emitter). A monotonic ``generation`` token drops results from a superseded scan
(task switch / re-scan / teardown) — the authoritative check runs on the GUI thread.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

from rpcoding.core.config import AppConfig
from rpcoding.core.session import SubjectSession
from rpcoding.core.tasks import Task

# Serial — keep this at 1. More concurrency does NOT help: Box's cloud filesystem serializes
# concurrent placeholder access, so parallel stat()s saturate and lock its driver, freezing the app
# and every other process touching the Box folder (the OS file explorer included).
_MAX_CONCURRENCY = 1


class _SubjectSignals(QObject):
    # (generation, subject, done, total, state, current_step) — state/current passed as ``object``
    # (an immutable enum / None), matching the dashboard's existing ``_step_tick`` convention.
    result = Signal(int, str, int, int, object, object)


class _SubjectRunnable(QRunnable):
    def __init__(
        self,
        config: AppConfig,
        task: Task,
        subject: str,
        generation: int,
        signals: _SubjectSignals,
        is_current: Callable[[], bool],
    ) -> None:
        super().__init__()
        self._config = config
        self._task = task
        self._subject = subject
        self._generation = generation
        self._signals = signals
        self._is_current = is_current

    def run(self) -> None:
        if not self._is_current():
            return  # superseded before we started — skip the Box I/O entirely
        try:
            done, total, state, current = SubjectSession(
                self._config, self._task, self._subject
            ).status()
        except OSError:
            return  # a cloud-sync placeholder we can't read yet; skip it this pass
        except Exception:  # noqa: BLE001 - a pool thread must never raise uncaught (would abort)
            return
        self._signals.result.emit(self._generation, self._subject, done, total, state, current)


class SubjectSummaryScanner(QObject):
    """Runs subject-status computation on a single background worker and re-emits each result on the
    GUI thread. Create it on (and parent it to) a main-thread widget."""

    # Re-emitted per subject, on the GUI thread: (generation, subject, done, total, state, current).
    subject_ready = Signal(int, str, int, int, object, object)
    scan_finished = Signal(int)  # (generation) — every subject of that scan has resolved

    def __init__(self, config: AppConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._generation = 0
        self._remaining = 0
        # Keep the per-subject emitters alive until their queued results are delivered.
        self._signals_alive: list[_SubjectSignals] = []
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(_MAX_CONCURRENCY)

    def set_config(self, config: AppConfig) -> None:
        self._config = config

    def start(self, task: Task, subjects: Iterable[str]) -> int:
        """Cancel any prior scan and fan out ``subjects``. Returns the new generation token."""
        subjects = list(subjects)
        gen = self._bump()
        self._remaining = len(subjects)
        if not subjects:
            self.scan_finished.emit(gen)
            return gen
        for sid in subjects:
            sig = _SubjectSignals()
            # Queued so the slot runs on this object's (the GUI) thread, not the pool thread.
            sig.result.connect(self._on_result, Qt.ConnectionType.QueuedConnection)
            self._signals_alive.append(sig)
            self._pool.start(
                _SubjectRunnable(
                    self._config,
                    task,
                    sid,
                    gen,
                    sig,
                    is_current=lambda g=gen: g == self._generation,
                )
            )
        return gen

    def cancel(self) -> None:
        """Invalidate in-flight results and drop queued-but-unstarted runnables."""
        self._bump()
        self._pool.clear()

    def shutdown(self) -> None:
        """Cancel, then wait for any already-running runnables so nothing emits into a torn-down
        object. Call from the owning window's ``closeEvent``."""
        self.cancel()
        self._pool.waitForDone(2000)

    def _bump(self) -> int:
        self._generation += 1
        self._signals_alive = []
        self._remaining = 0
        return self._generation

    @Slot(int, str, int, int, object, object)
    def _on_result(
        self, gen: int, subject: str, done: int, total: int, state: object, current: object
    ) -> None:
        if gen != self._generation:
            return  # a superseded scan; drop the late result
        self.subject_ready.emit(gen, subject, done, total, state, current)
        self._remaining -= 1
        if self._remaining <= 0:
            self.scan_finished.emit(gen)
