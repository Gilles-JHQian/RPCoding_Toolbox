"""Pure-Python pipeline library.

Nothing in ``rpcoding.core`` (or its submodules) may import PySide6/PyQt — the
core must stay headless and unit-testable without a GUI. Enforced by
``tests/test_core_has_no_qt.py``.
"""
