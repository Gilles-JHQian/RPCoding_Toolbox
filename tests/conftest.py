"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Run any Qt/GUI tests headlessly (no display needed).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Committed test fixtures (small label samples, synthetic .mat)."""
    return Path(__file__).parent / "fixtures"
