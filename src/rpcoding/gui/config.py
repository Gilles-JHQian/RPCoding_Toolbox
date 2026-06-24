"""Locate / load / save the GUI's AppConfig (data root + task map)."""

from __future__ import annotations

import json
import os
import re
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


def _subject_list_file(task: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", task)
    return config_dir() / f"subjects_{slug}.json"


def save_subject_list(task: str, subjects: list[str]) -> None:
    """Persist the checked subject IDs for ``task`` (the dashboard's 'Save list')."""
    path = _subject_list_file(task)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(subjects)), encoding="utf-8")


def load_subject_list(task: str) -> list[str] | None:
    """The saved checked subjects for ``task`` (None if never saved)."""
    path = _subject_list_file(task)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return [str(s) for s in data] if isinstance(data, list) else None
