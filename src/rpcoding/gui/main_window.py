"""Main window: a stacked dashboard + (placeholder) editor, with theme switching."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QStackedWidget

from rpcoding.core.config import AppConfig
from rpcoding.gui.dashboard import Dashboard
from rpcoding.gui.theme import DARK_THEME, LIGHT_THEME, Theme, qss


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, theme: Theme = DARK_THEME):
        super().__init__()
        self.setWindowTitle("RPCoding Toolbox")
        self.resize(1100, 720)
        self._theme = theme

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._dashboard = Dashboard(config, theme)
        self._dashboard.theme_toggle_requested.connect(self.toggle_theme)
        self._dashboard.open_editor.connect(self._open_editor)
        self._stack.addWidget(self._dashboard)

        self._editor_placeholder = QLabel("Annotation editor — built in the next branch")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._editor_placeholder)

        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss(theme))
        self._dashboard.apply_theme(theme)

    def toggle_theme(self) -> None:
        self.apply_theme(LIGHT_THEME if self._theme.name == "dark" else DARK_THEME)

    def _open_editor(self, session, step) -> None:  # noqa: ANN001 - Qt signal payloads
        self._stack.setCurrentWidget(self._editor_placeholder)
