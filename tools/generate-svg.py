#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

Point = Tuple[int, int]
Poly = List[Point]

# -----------------------------
# Grid / metrics (deduced)
# -----------------------------
CELL_W = 12

# Common viewBox HEIGHT for *all* characters (includes ascenders + descenders)
# Baseline at y=20, x-height starts at y=9. Ascender height above x-height is 9 units (0..9),
# so descender depth below baseline is also 9 units (20..29), plus 1 unit stroke thickness => y=30.
CELL_H = 30

# Horizontal stroke bands (1 unit thick)
Y_CAP0,  Y_CAP1  = 0, 1
Y_TOP0,  Y_TOP1  = 9, 10
Y_MID0,  Y_MID1  = 14, 15
Y_BASE0, Y_BASE1 = 19, 20
Y_DESC0, Y_DESC1 = 29, 30  # bottom-most thin band for descenders

# Connector band should align with the top of ascenders (same as cap band)
Y_LINK0, Y_LINK1 = Y_CAP0, Y_CAP1   # 0..1


def R(x1: int, y1: int, x2: int, y2: int) -> Poly:
    """Axis-aligned rectangle as a polygon (clockwise)."""
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


@dataclass(frozen=True)
class GlyphDef:
    width: int
    polys: List[Poly]


def poly_points(poly: Poly) -> str:
    return " ".join(f"{x},{y}" for x, y in poly)


# -----------------------------
# Simple transforms / helpers
# -----------------------------
def rotate180_poly(poly: Poly, w: int, cy2: int) -> Poly:
    """
    180° rotation around (w/2, cy2/2).
    For lowercase band center: cy2 = Y_TOP0 + Y_BASE1 (= 29).
    """
    return [(w - x, cy2 - y) for (x, y) in poly]


def mirrorx_poly(poly: Poly, w: int) -> Poly:
    """Mirror around vertical centerline x=w/2."""
    return [(w - x, y) for (x, y) in poly]


def translate_poly(poly: Poly, dx: int, dy: int = 0) -> Poly:
    return [(x + dx, y + dy) for (x, y) in poly]


# -----------------------------
# Base glyphs (letters)
# -----------------------------
GLYPHS: Dict[str, GlyphDef] = {}

# e (used to derive a)
E_DEF = GlyphDef(12, [
    R(0, Y_TOP0, 12, Y_TOP1),        # top bar
    R(0, Y_TOP1, 4,  Y_BASE0),       # left stem down
    R(8, Y_TOP1, 12, Y_MID0),        # upper-right closure (loop)
    R(0, Y_MID0, 12, Y_MID1),        # mid bar
    R(0, Y_BASE0, 12, Y_BASE1),      # baseline
])

# a = e rotated 180°
A_DEF = GlyphDef(12, [rotate180_poly(p, 12, Y_TOP0 + Y_BASE1) for p in E_DEF.polys])

# s (your step diagram)
S_DEF = GlyphDef(12, [
    R(0, Y_TOP0, 12, Y_TOP1),        # top bar
    R(0, Y_TOP1, 4,  Y_MID0),        # left vertical
    R(0, Y_MID0, 12, Y_MID1),        # mid bar
    R(8, Y_MID1, 12, Y_BASE0),       # right vertical
    R(0, Y_BASE0, 12, Y_BASE1),      # bottom bar
])

# z = mirrored s
Z_DEF = GlyphDef(12, [
    R(0, Y_TOP0, 12, Y_TOP1),        # top bar
    R(8, Y_TOP1, 12, Y_MID0),        # right vertical (upper)
    R(0, Y_MID0, 12, Y_MID1),        # mid bar
    R(0, Y_MID1, 4,  Y_BASE0),       # left vertical (lower)
    R(0, Y_BASE0, 12, Y_BASE1),      # bottom bar
])

GLYPHS.update({
    "a": A_DEF,

    "b": GlyphDef(12, [
        R(0, Y_CAP0, 4,  Y_BASE1),   # tall left stem
        R(4, Y_TOP0, 12, Y_TOP1),    # bowl top
        R(8, Y_TOP1, 12, Y_BASE0),   # bowl right
        R(4, Y_BASE0, 12, Y_BASE1),  # bowl bottom
    ]),

    "c": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "d": GlyphDef(12, [
        R(8, Y_CAP0, 12, Y_BASE1),
        R(0, Y_TOP0, 8,  Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(0, Y_BASE0, 8,  Y_BASE1),
    ]),

    "e": E_DEF,

    "f": GlyphDef(12, [
        R(4, Y_CAP0, 8,  Y_BASE1),   # main stem
        R(4, Y_CAP0, 12, Y_CAP1),    # cap bar (to the right)
        R(4, Y_TOP0, 12, Y_TOP1),    # x-height bar (to the right)
    ]),

    "g": GlyphDef(12, [
        # Row 1: xxx
        R(0, Y_TOP0, 12, Y_TOP1),

        # Row 2: xox
        R(0, Y_TOP1, 4,  Y_MID0),
        R(8, Y_TOP1, 12, Y_MID0),

        # Row 3: xxx
        R(0, Y_MID0, 12, Y_MID1),

        # Row 4: oox
        R(8, Y_MID1, 12, Y_BASE1),

        # Row 5: xxx
        R(0, Y_BASE1, 12, Y_BASE1 + 1),

        # Row 6: xox
        R(0, Y_BASE1 + 1, 4,  Y_BASE1 + 5),
        R(8, Y_BASE1 + 1, 12, Y_BASE1 + 5),

        # Row 7: xox
        R(0, Y_BASE1 + 5, 4,  Y_DESC0),
        R(8, Y_BASE1 + 5, 12, Y_DESC0),

        # Row 8: xxx
        R(0, Y_DESC0, 12, Y_DESC1),
    ]),

    "h": GlyphDef(12, [
        R(0, Y_CAP0, 4,  Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ]),

    "i": GlyphDef(12, [
        R(4, Y_TOP0, 8,  Y_BASE1),   # stem
        R(4, 0,      8,  4),         # square dot
    ]),

    "j": GlyphDef(12, [
        R(4, Y_TOP0, 8,  Y_DESC1),   # stem with descender
        R(4, 0,      8,  4),         # square dot
        R(0, Y_DESC0, 4,  Y_DESC1),  # thin hook to the left
    ]),

    "k": GlyphDef(12, [
        R(0, Y_CAP0, 4,  Y_BASE1),      # main stem |

        # right bar split (gap at mid band)
        R(8, Y_TOP0, 12, Y_MID0),       # upper right |
        R(8, Y_MID1, 12, Y_BASE1),      # lower right |

        # mid connector ONLY between stem and right bar boundary (like the x)
        R(4, Y_MID0, 8,  Y_MID1),       # |_  (doesn't fill 8..12)
    ]),

    "l": GlyphDef(12, [
        R(0, Y_CAP0, 4,  Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # m = double n (width 20)
    "m": GlyphDef(20, [
        R(0, Y_TOP0, 20, Y_TOP1),    # top bar across both humps
        R(0, Y_TOP0, 4,  Y_BASE1),   # left stem
        R(8, Y_TOP1, 12, Y_BASE1),   # middle stem
        R(16, Y_TOP1, 20, Y_BASE1),  # right stem
    ]),

    "n": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ]),

    "o": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # p = like o, with left stem descender
    "p": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_DESC1),   # descender
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # q = mirror of p
    "q": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(8, Y_TOP1, 12, Y_DESC1),   # descender
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # r = only stem + top bar
    "r": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
    ]),

    "s": S_DEF,

    # t = stem + bars at x-height and baseline (to the right)
    "t": GlyphDef(12, [
        R(4, Y_CAP0, 8,  Y_BASE1),   # stem
        R(8, Y_TOP0, 12, Y_TOP1),    # x-height bar (right)
        R(8, Y_BASE0, 12, Y_BASE1),  # baseline bar (right)
    ]),

    "u": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "v": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_MID1),        # left stem (top -> mid)
        R(8, Y_TOP0, 12, Y_MID1),        # right stem (top -> mid)
        R(0, Y_MID0, 12, Y_MID1),        # wide part in the middle  _|_
        R(4, Y_MID1, 8,  Y_BASE1),       # narrow stem below the middle   |
    ]),

    # w = double u (width 20)
    "w": GlyphDef(20, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(16, Y_TOP0, 20, Y_BASE1),
        R(0, Y_BASE0, 20, Y_BASE1),
    ]),

    "x": GlyphDef(12, [
        # left bar, split above/below the mid band
        R(0, Y_TOP0, 4,  Y_MID0),
        R(0, Y_MID1, 4,  Y_BASE1),

        # right bar, split above/below the mid band
        R(8, Y_TOP0, 12, Y_MID0),
        R(8, Y_MID1, 12, Y_BASE1),

        # mid connector (bridges the gap)
        R(4, Y_MID0, 8,  Y_MID1),
    ]),

    # y = u with right stem descender
    "y": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(8, Y_TOP0, 12, Y_DESC1),   # descender
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "z": Z_DEF,
})

# -----------------------------
# Digits 0–9
# -----------------------------
GLYPHS.update({
    "0": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
    "1": GlyphDef(12, [
        R(4, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
        # bottom bar removed later in your flow; keeping as-is here in this script snapshot
        R(4, Y_BASE0, 12, Y_BASE1),
    ]),
    "2": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_MID0),
        R(0, Y_MID0, 12, Y_MID1),
        R(0, Y_MID1, 4,  Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
    "3": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_MID0),
        R(0, Y_MID0, 12, Y_MID1),
        R(8, Y_MID1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
    "4": GlyphDef(12, [
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_TOP0, 4,  Y_MID1),
        R(0, Y_MID0, 12, Y_MID1),
    ]),
    "5": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_MID0),
        R(0, Y_MID0, 12, Y_MID1),
        R(8, Y_MID1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
    "6": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE1),
        R(0, Y_MID0, 12, Y_MID1),
        R(8, Y_MID1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
    "7": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ]),
    "8": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_MID0, 12, Y_MID1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
    "9": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
        R(0, Y_TOP1, 4,  Y_MID0),
        R(0, Y_MID0, 12, Y_MID1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),
})

# -----------------------------
# Ligatures
# -----------------------------
def compose_ligature_overlap(left_key: str, right_key: str, *, overlap: int = 4) -> GlyphDef:
    """Tight ligature: overlap the two glyph cells."""
    left = GLYPHS[left_key]
    right = GLYPHS[right_key]
    dx = left.width - overlap
    width = left.width + right.width - overlap
    polys = list(left.polys) + [translate_poly(p, dx, 0) for p in right.polys]
    return GlyphDef(width, polys)


def ligature_st_like(left_key: str, right_key: str, *, gap: int = 4, right_touch_x: int = 1) -> GlyphDef:
    """
    'st-like' ligature connector:
      - start at x-height bottom edge (y=Y_TOP1 == 10)
      - go UP to the *bottom* of the top band (y=Y_LINK1 == 1)
      - then go RIGHT along the top band (y=0..1) into the right glyph

    IMPORTANT:
      We intentionally do NOT overlap the vertical connector with the top horizontal band.
      This makes the corner align perfectly under variable scaling.
    """
    left = GLYPHS[left_key]
    right = GLYPHS[right_key]

    dx = left.width + gap
    width = left.width + gap + right.width

    polys = list(left.polys) + [translate_poly(p, dx, 0) for p in right.polys]

    # Vertical connector: 1 unit wide, from y=1 down to y=10
    x0 = left.width
    x1 = left.width + 1
    polys.append(R(x0, Y_LINK1, x1, Y_TOP1))

    # Horizontal connector: along top band y=0..1, reaching into the right glyph
    h_x0 = left.width
    h_x1 = dx + max(1, right_touch_x)
    polys.append(R(h_x0, Y_LINK0, h_x1, Y_LINK1))

    return GlyphDef(width, polys)


# Build 'st' using the same st-like logic (gap=0), so the thin vertical connector is a true 1-unit rectangle
# and can behave consistently under variable width rules.
# We want the top connector to reach the left edge of the 't' stem, which starts at x=4 inside 't' => right_touch_x=4.
GLYPHS["st"] = ligature_st_like("s", "t", gap=0, right_touch_x=4)

# Tight overlap ligatures
GLYPHS["fi"] = compose_ligature_overlap("f", "i", overlap=4)
GLYPHS["ij"] = compose_ligature_overlap("i", "j", overlap=4)

# 'st-like' ligatures: spaced + corner connector
GLYPHS["ch"] = ligature_st_like("c", "h", gap=4, right_touch_x=1)
GLYPHS["sh"] = ligature_st_like("s", "h", gap=4, right_touch_x=1)
# t's x-height bar is at x=8..12, so reach 8 units into the right glyph to touch it
GLYPHS["ct"] = ligature_st_like("c", "t", gap=4, right_touch_x=8)

# -----------------------------
# SVG rendering / writing
# -----------------------------
def render_glyph_svg(key: str, g: GlyphDef) -> str:
    vb = f"0 0 {g.width} {CELL_H}"
    polys = "\n".join(
        f'    <polygon class="{key}" points="{poly_points(poly)}"/>'
        for poly in g.polys
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb}" width="{g.width}" height="{CELL_H}" shape-rendering="crispEdges">\n'
        "  <g>\n"
        f"{polys}\n"
        "  </g>\n"
        "</svg>\n"
    )


def project_root() -> Path:
    # Script lives in a subfolder => project root is exactly one directory above script folder
    return Path(__file__).resolve().parent.parent


def write_all_svgs() -> None:
    root = project_root()
    out_dir = root / "src"
    out_dir.mkdir(parents=True, exist_ok=True)

    keys = list("abcdefghijklmnopqrstuvwxyz0123456789") + ["st", "ch", "ct", "fi", "ij", "sh"]
    for key in keys:
        g = GLYPHS.get(key)
        if not g:
            raise KeyError(f"Missing glyph: {key}")

        svg = render_glyph_svg(key, g)
        (out_dir / f"character-{key}.svg").write_text(svg, encoding="utf-8")

    print(f"Wrote {len(keys)} SVGs to: {out_dir}")


if __name__ == "__main__":
    write_all_svgs()
