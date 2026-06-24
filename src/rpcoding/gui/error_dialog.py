"""Last-resort error surfacing: a global excepthook + a reusable error dialog.

An uncaught exception in a Qt slot/callback otherwise tears the whole app down (PySide6 aborts on
an exception that escapes the event loop). Installing :func:`install_excepthook` turns that into a
non-fatal dialog showing the traceback, so the app stays alive and the error is debuggable.
"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox


def format_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def show_error(message: str, detail: str = "", *, title: str = "Error", parent=None) -> None:
    """Show a non-fatal error dialog; ``detail`` (traceback/log) goes in the expandable section."""
    if QApplication.instance() is None:  # headless / tests: nothing to show on
        return
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(message)
    if detail:
        box.setDetailedText(detail)
    box.exec()


def install_excepthook() -> None:
    """Route uncaught exceptions to a dialog (and stderr) instead of aborting the app."""

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        traceback.print_exception(exc_type, exc, tb)  # keep the console log for CI / terminals
        try:
            detail = "".join(traceback.format_exception(exc_type, exc, tb))
            show_error(
                "An unexpected error occurred — the app is still running.",
                detail,
                title="Unexpected error",
            )
        except Exception:  # noqa: BLE001 - the handler must never raise
            pass

    sys.excepthook = hook
