"""Lightweight progress reporting shared by the pipeline runner and the GUI.

A :data:`Reporter` is just ``callable(fraction, message)`` where ``fraction`` is in ``[0, 1]`` (or
``None`` for indeterminate work) and ``message`` describes the current phase. Step actions call it
as they go; the runner composes per-step reporters into pipeline-level :class:`StepProgress` events
so a batch UI can show which subject is on which step and how far that step has got.

This module deliberately has no heavy imports (no Qt, no steps) so any layer can depend on it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpcoding.core.steps import Step

# fraction in [0, 1], or None for indeterminate; message = human-facing phase description
Reporter = Callable[["float | None", str], None]


def noop(fraction: float | None, message: str) -> None:
    """A reporter that discards everything (the default when no progress sink is wired)."""


def clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def sub(report: Reporter | None, lo: float, hi: float) -> Reporter:
    """A child reporter whose ``[0, 1]`` is mapped into the parent's ``[lo, hi]`` slice.

    Used to compose a multi-phase step: e.g. concatenation can report 0..1 over its read loop while
    occupying only the first 80% of the parent step's bar. ``None`` (indeterminate) passes through.
    """
    parent = report or noop
    span = hi - lo

    def _mapped(fraction: float | None, message: str) -> None:
        parent(None if fraction is None else lo + clamp01(fraction) * span, message)

    return _mapped


@dataclass(frozen=True)
class StepProgress:
    """One progress tick from :func:`rpcoding.core.runner.run_pipeline`.

    Carries both the within-step position (``fraction``/``message``) and the pipeline position
    (``index``/``total``) so a batch view can render "step 3/6 — <phase>" with a per-step bar.
    """

    step: Step
    index: int  # 1-based position among the steps that run in this pass
    total: int  # number of steps that will run in this pass (best-effort)
    fraction: float | None  # progress within the current step (0..1, or None = indeterminate)
    message: str  # phase description
    title: str  # the step's human-facing title

    @property
    def overall(self) -> float:
        """Fraction across the whole pipeline (0..1), each step an equal slice."""
        if self.total <= 0:
            return 0.0
        base = (self.index - 1) / self.total
        frac = self.fraction if self.fraction is not None else 0.0
        return clamp01(base + clamp01(frac) / self.total)
