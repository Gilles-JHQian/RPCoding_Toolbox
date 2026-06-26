"""GUI entry point (``rpcoding-gui``)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from rpcoding.core.config import AppConfig
from rpcoding.gui.config import load_config, save_config
from rpcoding.gui.error_dialog import install_excepthook
from rpcoding.gui.loading_dialog import LoadingDialog
from rpcoding.gui.main_window import MainWindow
from rpcoding.gui.theme import DARK_THEME, qss


def _ensure_config() -> AppConfig | None:
    config = load_config()
    if config is not None and Path(config.droot).exists():
        return config
    chosen = QFileDialog.getExistingDirectory(None, "Select the CoganLab data root ($BOX/CoganLab)")
    if not chosen:
        return None
    config = AppConfig(droot=Path(chosen))
    save_config(config)
    return config


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    install_excepthook()  # an uncaught slot exception should pop a dialog, not kill the app
    config = _ensure_config()  # may pop a folder picker on first run — before the splash
    if config is None:
        return 0
    # A small splash while the main window is built, so startup isn't a blank wait.
    app.setStyleSheet(qss(DARK_THEME))  # style the splash before the window applies the theme
    splash = LoadingDialog("Starting RPCoding Toolbox…")
    splash.set_progress(15, "Building the interface…")
    splash.show_centered()
    app.processEvents()  # paint the splash before the blocking construction below
    window = MainWindow(config, DARK_THEME)
    splash.set_progress(100, "Ready")
    app.processEvents()
    window.show()
    splash.close()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
