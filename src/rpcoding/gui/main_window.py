"""Main window: a stacked dashboard + audio editor, with theme switching."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.gui.dashboard import Dashboard
from rpcoding.gui.editor import AudioEditor
from rpcoding.gui.editor_loader import tiers_for_step
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

        self._editor = AudioEditor(theme)
        self._editor.saved.connect(self._on_editor_saved)
        self._editor.back_requested.connect(self._show_dashboard)
        self._stack.addWidget(self._editor)
        self._editing: tuple | None = None  # (SubjectSession, Step) currently open in the editor

        # Esc returns to the dashboard from the editor.
        back = QShortcut(QKeySequence("Escape"), self)
        back.activated.connect(self._show_dashboard)

        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss(theme))
        self._dashboard.apply_theme(theme)
        self._editor.set_theme(theme)

    def toggle_theme(self) -> None:
        self.apply_theme(LIGHT_THEME if self._theme.name == "dark" else DARK_THEME)

    def _open_editor(self, session, step) -> None:  # noqa: ANN001 - Qt signal payloads
        self._editing = (session, step)
        specs, save_path = tiers_for_step(session.results_dir, step)
        self._editor.set_tiers(specs)
        self._editor.configure_save(save_path)
        wav = session.output_path(paths.ALLBLOCKS_WAV)
        if wav.exists():
            self._editor.load(wav, session.results_dir / ".rpcoding" / "cache")
        self._stack.setCurrentWidget(self._editor)
        self._editor.setFocus()

    def _on_editor_saved(self) -> None:
        if self._editing is None:
            return
        session, step = self._editing
        session.record_done(step)
        self._dashboard.refresh()

    def _show_dashboard(self) -> None:
        self._stack.setCurrentWidget(self._dashboard)
