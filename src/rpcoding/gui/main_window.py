"""Main window (the dashboard) plus a separate top-level annotation-editor window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

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
        self.resize(1180, 740)
        self._theme = theme

        self._dashboard = Dashboard(config, theme)
        self._dashboard.theme_toggle_requested.connect(self.toggle_theme)
        self._dashboard.open_editor.connect(self._open_editor)
        self.setCentralWidget(self._dashboard)

        # The editor is a separate top-level window (created once, reused), hidden until opened.
        # Parented to the main window with a Window flag so it's a real window but still owned
        # (destroyed with the app) rather than leaking.
        self._editor = AudioEditor(theme, parent=self)
        self._editor.setWindowFlag(Qt.WindowType.Window, True)
        self._editor.resize(1240, 820)
        self._editor.saved.connect(self._on_editor_saved)
        self._editor.back_requested.connect(self._close_editor)
        self._editor.theme_toggle_requested.connect(self.toggle_theme)
        self._editing: tuple | None = None  # (SubjectSession, Step) currently open in the editor

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
        title = f"{session.subject} · {step.value} — Annotation Editor"
        self._editor.setWindowTitle(title)
        self._editor.set_tiers(specs)
        self._editor.configure_save(save_path)
        # After MFA has denoised allblocks.wav in place, prefer the preserved original unless the
        # user opted into the processed audio (Settings → MFA).
        wav = session.output_path(paths.ALLBLOCKS_WAV)
        original = session.output_path(paths.ALLBLOCKS_ORIGINAL_WAV)
        if not session.config.editor_use_processed_audio and original.exists():
            wav = original
        if wav.exists():
            self._editor.load(wav, session.results_dir / ".rpcoding" / "cache")
        self._editor.show()
        self._editor.raise_()
        self._editor.activateWindow()
        self._editor.setFocus()

    def _on_editor_saved(self) -> None:
        if self._editing is None:
            return
        session, step = self._editing
        session.record_done(step)
        self._dashboard.refresh()

    def _close_editor(self) -> None:
        self._editor.hide()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._editor.close()
        super().closeEvent(event)
