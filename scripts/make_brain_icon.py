"""Generate the app's brain icon (brain.png + brain.ico) into rpcoding/gui/assets/.

A simplified take on the reference art: a cute pink brain with gyri folds and a calm closed-eye
smile, on a cream rounded tile — without the busy meditation pose / waveform clutter. Drawn with PIL
primitives, supersampled then downscaled for smooth edges.

    python scripts/make_brain_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "rpcoding" / "gui" / "assets"

CREAM = (247, 242, 234, 255)
PINK = (240, 167, 182, 255)
PINK_EDGE = (214, 122, 142, 255)
FOLD = (221, 138, 156, 255)
FACE = (122, 74, 84, 255)
SS = 4  # supersample factor


def _bumps(cx, cy, rx, ry, n):
    return [
        (cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def _blob(d, color, cx, cy, rx, ry, n, br):
    """A lumpy blob = a core ellipse + bump circles around its rim (the brain's walnut outline)."""
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color)
    for bx, by in _bumps(cx, cy, rx, ry, n):
        d.ellipse([bx - br, by - br, bx + br, by + br], fill=color)


def make() -> Image.Image:
    s = 256 * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8 * SS, 8 * SS, s - 8 * SS, s - 8 * SS], radius=48 * SS, fill=CREAM)

    cx, cy = s / 2, 116 * SS
    rx, ry, n = 78 * SS, 64 * SS, 13
    br = 26 * SS
    _blob(d, PINK_EDGE, cx, cy, rx, ry, n, br)  # darker rim
    _blob(d, PINK, cx, cy, rx - 6 * SS, ry - 6 * SS, n, br - 6 * SS)  # fill (inset = outline)

    # gyri folds
    pen = dict(fill=FOLD, width=5 * SS)
    d.line([cx, cy - ry + 8 * SS, cx, cy + 12 * SS], **pen)  # central sulcus (stops above the face)
    for side in (-1, 1):
        for dy, w in ((-30, 34), (2, 40), (32, 32)):
            ex = cx + side * w * SS
            yy = cy + dy * SS
            a = cx + side * 12 * SS
            box = [min(a, ex), yy - 16 * SS, max(a, ex), yy + 16 * SS]
            d.arc(box, start=110 if side < 0 else -70, end=250 if side < 0 else 70, **pen)

    # calm closed-eye smile, sitting on the lower face of the brain
    eye_y = cy + 30 * SS
    for side in (-1, 1):
        ex = cx + side * 34 * SS
        eye = [ex - 18 * SS, eye_y - 12 * SS, ex + 18 * SS, eye_y + 14 * SS]
        d.arc(eye, 200, 340, fill=FACE, width=5 * SS)
    d.arc(
        [cx - 22 * SS, eye_y + 18 * SS, cx + 22 * SS, eye_y + 46 * SS],
        20,
        160,
        fill=FACE,
        width=5 * SS,
    )

    return img.resize((256, 256), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = make()
    img.save(OUT / "brain.png")
    img.save(
        OUT / "brain.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"wrote {OUT/'brain.png'} and {OUT/'brain.ico'}")


if __name__ == "__main__":
    main()
