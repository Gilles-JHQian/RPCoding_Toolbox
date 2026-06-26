"""Bundled GUI assets (the app/brain icon) + helpers to locate them."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def icon_path() -> Path:
    """Path to the app icon PNG (window + taskbar)."""
    return Path(str(files(__package__) / "brain.png"))


def ico_path() -> Path:
    """Path to the multi-size Windows ICO (for launcher shortcuts)."""
    return Path(str(files(__package__) / "brain.ico"))
