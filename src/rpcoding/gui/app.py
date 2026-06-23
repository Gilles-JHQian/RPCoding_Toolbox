"""GUI entry point (``rpcoding-gui``)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from rpcoding.core.config import AppConfig
from rpcoding.gui.config import load_config, save_config
from rpcoding.gui.main_window import MainWindow
from rpcoding.gui.theme import DARK_THEME


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
    config = _ensure_config()
    if config is None:
        return 0
    window = MainWindow(config, DARK_THEME)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
