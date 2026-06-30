"""Main window (the dashboard) plus a separate top-level annotation-editor window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow

from rpcoding.core import paths
from rpcoding.core.config import AppConfig
from rpcoding.core.rpcode.errors import response_tags
from rpcoding.core.steps import Step
from rpcoding.gui.assets import icon_path
from rpcoding.gui.dashboard import Dashboard
from rpcoding.gui.error_dialog import show_error
from rpcoding.gui.hover_cursor import install_hover_cursor
from rpcoding.gui.loading_dialog import LoadingDialog
from rpcoding.gui.theme import DARK_THEME, LIGHT_THEME, Theme, qss


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, theme: Theme = DARK_THEME):
        super().__init__()
        self.setWindowTitle("Cogan Lab RP Coding Toolbox")
        if icon_path().exists():
            self.setWindowIcon(QIcon(str(icon_path())))
        self.resize(1180, 740)
        self._theme = theme

        # Pointing-hand cursor on every clickable widget (app-wide event filter).
        app = QApplication.instance()
        self._hover_cursor = install_hover_cursor(app) if app is not None else None

        self._dashboard = Dashboard(config, theme)
        self._dashboard.theme_toggle_requested.connect(self.toggle_theme)
        self._dashboard.open_editor.connect(self._open_editor)
        self._dashboard.open_clock_editor.connect(self._open_clock_editor)
        self.setCentralWidget(self._dashboard)

        # The editor is built lazily on first open: importing it pulls pyqtgraph + scipy.signal
        # (~0.7 s) and constructing it is ~0.25 s, all of which would otherwise slow every launch.
        self._editor = None
        self._editing: tuple | None = None  # (SubjectSession, Step) currently open in the editor
        self._loading: LoadingDialog | None = None

        self.apply_theme(theme)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss(theme))
        self._dashboard.apply_theme(theme)
        if self._editor is not None:
            self._editor.set_theme(theme)

    def toggle_theme(self) -> None:
        self.apply_theme(LIGHT_THEME if self._theme.name == "dark" else DARK_THEME)

    def _ensure_editor(self):
        """Import + construct the audio editor on first use (kept off startup — see __init__)."""
        if self._editor is not None:
            return self._editor
        from rpcoding.gui.editor import AudioEditor  # heavy import (pyqtgraph + scipy.signal)

        ed = AudioEditor(self._theme, parent=self)
        ed.setWindowFlag(Qt.WindowType.Window, True)  # a real, owned window
        ed.resize(1240, 820)
        ed.saved.connect(self._on_editor_saved)
        ed.denoised.connect(self._on_denoised)
        ed.back_requested.connect(self._close_editor)
        ed.theme_toggle_requested.connect(self.toggle_theme)
        ed.load_progress.connect(self._on_editor_load_progress)
        ed.load_finished.connect(self._on_editor_loaded)
        ed.load_failed.connect(self._on_editor_load_failed)
        self._editor = ed
        return ed

    def _open_editor(self, session, step) -> None:  # noqa: ANN001 - Qt signal payloads
        from rpcoding.gui.editor_loader import tiers_for_step

        specs, save_path = tiers_for_step(session.results_dir, step)
        self._open_editor_with(
            session,
            step,
            specs,
            save_path,
            f"{session.subject} · {step.value} — Annotation Editor",
        )

    def _open_clock_editor(self, session) -> None:  # noqa: ANN001 - Qt signal payload
        """Open the editor to mark clock-drift anchors (no pipeline step is recorded on save)."""
        from rpcoding.gui.editor_loader import tiers_for_clock_anchors

        specs, save_path = tiers_for_clock_anchors(session.results_dir)
        self._open_editor_with(
            session,
            None,
            specs,
            save_path,
            f"{session.subject} · clock drift — drag anchors onto the true stimulus",
        )

    def _open_editor_with(self, session, step, specs, save_path, title) -> None:
        # Show the popup right away: the first open imports + builds the (heavy) editor, then
        # renders the audio — so there's feedback during that work, not a frozen, blank wait.
        self._loading = LoadingDialog("Loading editor…", self)
        self._loading.set_busy("Preparing editor…")
        self._loading.show_centered()
        QApplication.processEvents()  # paint the popup before the blocking import/build below

        editor = self._ensure_editor()
        self._editing = (session, step)  # step None = clock-anchor mode (no step recorded on save)
        editor.setWindowTitle(title)
        editor.set_tiers(specs)
        editor.set_response_tags(response_tags(session.task))  # per-task quick-tag palette
        editor.configure_save(save_path)
        editor.configure_denoise(
            session.output_path(paths.ALLBLOCKS_WAV),
            session.output_path(paths.ALLBLOCKS_ORIGINAL_WAV),
        )
        wav = self._editor_wav(session)
        if wav is None:
            self._close_loading()
            self._reveal_editor()  # nothing to render, just open
            return
        # Render in the background; the popup tracks progress and the editor is revealed once ready.
        self._loading.set_progress(0, "Loading audio…")
        editor.load(wav, session.results_dir / ".rpcoding" / "cache")

    def _reveal_editor(self) -> None:
        self._editor.show()
        self._editor.raise_()
        self._editor.activateWindow()
        self._editor.setFocus()

    def _close_loading(self) -> None:
        if self._loading is not None:
            self._loading.close()
            self._loading = None

    def _on_editor_load_progress(self, pct: int, message: str) -> None:
        if self._loading is not None:
            self._loading.set_progress(pct, message)

    def _on_editor_loaded(self) -> None:
        # Only relevant while opening (self._loading set); an in-editor reload (e.g. denoise) leaves
        # the already-shown editor alone.
        if self._loading is not None:
            self._close_loading()
            self._reveal_editor()

    def _on_editor_load_failed(self, message: str) -> None:
        was_opening = self._loading is not None
        self._close_loading()
        if was_opening:
            self._reveal_editor()
        show_error("Could not load the audio", message, parent=self)

    @staticmethod
    def _exists(p) -> bool:
        """``p.exists()`` that treats an un-stat-able cloud placeholder (OSError) as absent."""
        try:
            return p.exists()
        except OSError:
            return False

    def _editor_wav(self, session):
        """Which audio the editor should load. MFA denoises allblocks.wav in place and keeps the
        pre-denoise audio as allblocks_original.wav; unless the user explicitly opts into the
        processed audio (Settings → MFA), load that original so the spectrogram shows the raw
        signal. Falls back to allblocks.wav (which *is* the original when MFA never denoised it)."""
        allblocks = session.output_path(paths.ALLBLOCKS_WAV)
        original = session.output_path(paths.ALLBLOCKS_ORIGINAL_WAV)
        if not session.config.editor_use_processed_audio and self._exists(original):
            return original
        return allblocks if self._exists(allblocks) else None

    def _on_editor_saved(self) -> None:
        if self._editing is None:
            return
        session, step = self._editing
        if step is not None:  # clock-anchor mode (step None) just persists clock_anchors.txt
            session.record_done(step)
        self._dashboard.refresh()

    def _on_denoised(self) -> None:
        """Noise reduction was applied in the editor — mark the Denoise step done (whatever step
        opened the editor) and refresh the dashboard."""
        if self._editing is None:
            return
        session, _step = self._editing
        session.record_done(Step.DENOISE)
        self._dashboard.refresh()

    def _close_editor(self) -> None:
        if self._editor is not None:
            self._editor.hide()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._editor is not None:
            self._editor.close()
        super().closeEvent(event)
