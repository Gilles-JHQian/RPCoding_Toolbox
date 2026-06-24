"""A minimal QObject worker + helper to run a callable on a QThread.

Signals: ``progress(int, str)``, ``result(object)``, ``error(str)``, ``finished()``. Never touch
widgets from inside the worker callable — communicate via signals.

Callbacks passed to :func:`run_in_thread` are always invoked **on the main (GUI) thread**, so they
may safely touch widgets. This is not automatic: connecting a signal to a bare Python callable
(a closure/free function, not a bound method of a main-thread ``QObject``) gives a *direct*
connection, so the callable would run in the **worker** thread — and touching a widget from there
is undefined behaviour that hard-crashes the app (a C++ abort the Python excepthook can't catch).
We avoid that by relaying through a ``_Dispatcher`` ``QObject`` that lives in the parent's thread.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot


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


class _Dispatcher(QObject):
    """Relays worker signals to plain callbacks. Lives in the parent's (main) thread, so the
    cross-thread signal delivery is queued onto that thread — the callbacks run there, not on the
    worker thread, even when they are bare closures."""

    def __init__(
        self,
        parent: QObject,
        on_result: Callable | None,
        on_error: Callable | None,
        on_finished: Callable | None,
    ) -> None:
        super().__init__(parent)
        self._on_result = on_result
        self._on_error = on_error
        self._on_finished = on_finished

    @Slot(object)
    def result(self, value: object) -> None:
        if self._on_result is not None:
            self._on_result(value)

    @Slot(str)
    def error(self, message: str) -> None:
        if self._on_error is not None:
            self._on_error(message)

    @Slot()
    def finished(self) -> None:
        if self._on_finished is not None:
            self._on_finished()


# Keep (thread, worker, dispatcher) tuples alive until they finish so Python GC can't collect a
# running worker (or the dispatcher that delivers its callbacks).
_ACTIVE: set[tuple[QThread, Worker, _Dispatcher]] = set()


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

    ``on_result``/``on_error``/``on_finished`` run on ``parent``'s thread (the GUI thread) and may
    touch widgets directly — see the module docstring. The caller keeps a reference (e.g. on
    ``parent``) so the thread isn't garbage-collected.
    """
    thread = QThread(parent)
    worker = Worker(fn, *args, **kwargs)
    worker.moveToThread(thread)
    # The dispatcher lives in parent's (main) thread, so worker.<sig> -> dispatcher.<slot> is a
    # queued cross-thread call: the callbacks fire on the main thread.
    dispatcher = _Dispatcher(parent, on_result, on_error, on_finished)
    thread.started.connect(worker.run)
    worker.result.connect(dispatcher.result)
    worker.error.connect(dispatcher.error)
    worker.finished.connect(dispatcher.finished)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    holder = (thread, worker, dispatcher)
    _ACTIVE.add(holder)
    thread.finished.connect(lambda: _ACTIVE.discard(holder))

    thread.start()
    return thread, worker
