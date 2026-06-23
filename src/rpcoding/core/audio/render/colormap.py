"""Magma colormap (from the design tokens) as a Qt-free ``(256, 3) uint8`` lookup table."""

from __future__ import annotations

import numpy as np

# 9 magma anchors (0->1 intensity), from the design handoff.
_MAGMA_RGB = np.array(
    [
        [0, 0, 4],
        [28, 16, 68],
        [79, 18, 123],
        [129, 37, 129],
        [181, 54, 122],
        [229, 80, 100],
        [251, 135, 97],
        [254, 194, 135],
        [252, 253, 191],
    ],
    dtype=np.float64,
)


def _build_lut(stops: np.ndarray, n: int = 256) -> np.ndarray:
    xp = np.linspace(0.0, 1.0, len(stops))
    x = np.linspace(0.0, 1.0, n)
    lut = np.empty((n, 3), dtype=np.uint8)
    for c in range(3):
        lut[:, c] = np.clip(np.round(np.interp(x, xp, stops[:, c])), 0, 255).astype(np.uint8)
    return lut


MAGMA_LUT: np.ndarray = _build_lut(_MAGMA_RGB)
MAGMA_STOPS: list[tuple[int, int, int]] = [tuple(int(v) for v in row) for row in _MAGMA_RGB]
