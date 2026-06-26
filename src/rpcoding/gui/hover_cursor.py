"""App-wide pointing-hand cursor for clickable widgets on hover.

Qt stylesheets can't set a hover cursor, and setting it on every button by hand misses dynamically
created ones (dialogs, step rows). One application event filter covers them all: on mouse-enter a
button/combo gets the pointing-hand cursor (or the arrow when it's disabled).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractButton, QComboBox

_CLICKABLE = (QAbstractButton, QComboBox)


class HoverCursorFilter(QObject):
    """Event filter giving buttons/combos the pointing-hand cursor on hover."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt override
        if event.type() == QEvent.Type.Enter and isinstance(obj, _CLICKABLE):
            shape = (
                Qt.CursorShape.PointingHandCursor if obj.isEnabled() else Qt.CursorShape.ArrowCursor
            )
            obj.setCursor(shape)
        return super().eventFilter(obj, event)


def install_hover_cursor(app) -> HoverCursorFilter:
    """Install the hover-cursor filter on ``app`` and return it (kept alive by parenting to app)."""
    filt = HoverCursorFilter(app)
    app.installEventFilter(filt)
    return filt
