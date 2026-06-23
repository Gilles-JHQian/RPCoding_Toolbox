"""A minimal QObject worker + helper to run a callable on a QThread.

Signals: ``progress(int, str)``, ``result(object)``, ``error(str)``, ``finished()``. Never touch
widgets from inside the worker callable — communicate via signals.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

# Keep (thread, worker) pairs alive until they finish so Python GC can't collect a running worker.
_ACTIVE: set[tuple[QThread, Worker]] = set()


class Worker(QObject):
    progress = Signal(int, str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            value = self._fn(*self._args, **self._kwargs)
            self.result.emit(value)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI via the error signal
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


def run_in_thread(
    parent: QObject,
    fn: Callable,
    *args,
    on_result: Callable | None = None,
    on_error: Callable | None = None,
    on_finished: Callable | None = None,
    **kwargs,
) -> tuple[QThread, Worker]:
    """Run ``fn`` on a background QThread; wire optional callbacks. Returns (thread, worker).

    The caller keeps a reference (e.g. on ``parent``) so the thread isn't garbage-collected.
    """
    thread = QThread(parent)
    worker = Worker(fn, *args, **kwargs)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    if on_result is not None:
        worker.result.connect(on_result)
    if on_error is not None:
        worker.error.connect(on_error)
    if on_finished is not None:
        worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    holder = (thread, worker)
    _ACTIVE.add(holder)
    thread.finished.connect(lambda: _ACTIVE.discard(holder))

    thread.start()
    return thread, worker
