"""Smoke tests: the package imports and the CLI runs."""

from __future__ import annotations

import rpcoding


def test_version_present():
    assert isinstance(rpcoding.__version__, str)
    assert rpcoding.__version__


def test_cli_help_runs():
    from rpcoding.cli.main import main

    assert main([]) == 0
