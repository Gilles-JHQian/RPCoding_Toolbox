"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Committed test fixtures (small label samples, synthetic .mat)."""
    return Path(__file__).parent / "fixtures"
