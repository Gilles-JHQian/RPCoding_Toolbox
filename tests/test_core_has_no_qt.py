"""Guard: importing ``rpcoding.core`` (and every submodule) must never pull in Qt.

This keeps the core pipeline headless and unit-testable without a display/GUI.

The check runs in a *fresh* subprocess so test-time plugins (e.g.
``pytest-qt``, which imports PySide6 at startup) don't pollute ``sys.modules``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_CHECK = """
import importlib, pkgutil, sys
import rpcoding.core

for mod in pkgutil.walk_packages(rpcoding.core.__path__, prefix="rpcoding.core."):
    importlib.import_module(mod.name)

prefixes = ("PySide6", "PyQt5", "PyQt6")
offenders = sorted(m for m in sys.modules if m.startswith(prefixes))
if offenders:
    print("QT_IMPORTED:" + ",".join(offenders))
    raise SystemExit(1)
"""


def test_core_does_not_import_qt():
    env = dict(os.environ)
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-c", _CHECK],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        "rpcoding.core must not import Qt.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
