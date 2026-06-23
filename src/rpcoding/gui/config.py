"""Locate / load / save the GUI's AppConfig (data root + task map)."""

from __future__ import annotations

import os
from pathlib import Path

from rpcoding.core.config import AppConfig


def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "rpcoding"


def config_file() -> Path:
    return config_dir() / "config.json"


def load_config() -> AppConfig | None:
    path = config_file()
    return AppConfig.load(path) if path.exists() else None


def save_config(config: AppConfig) -> None:
    config.save(config_file())
