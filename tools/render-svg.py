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
# Default lowercase cell width
CELL_W = 12

# Common viewBox HEIGHT for *all* characters (includes ascenders + descenders)
# Baseline at y=20, x-height starts at y=9. Ascender height above x-height is 9 units (0..9),
# so descender depth below baseline is also 9 units (20..29), plus 1 unit stroke thickness => y=30.
CELL_H = 30

# Horizontal strokes are 1 unit thick at these bands
Y_CAP0,  Y_CAP1  = 0, 1
Y_TOP0,  Y_TOP1  = 9, 10
Y_MID0,  Y_MID1  = 14, 15
Y_BASE0, Y_BASE1 = 19, 20
Y_DESC0, Y_DESC1 = 29, 30  # bottom-most thin band for descenders


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
# Simple transforms
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

# a = e rotated 180° (your latest rule)
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

    # g: placeholder (we’ll refine later)
    "g": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
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
        R(0, Y_CAP0, 4,  Y_BASE1),
        R(4, Y_TOP1, 12, Y_MID0),
        R(4, Y_MID1, 12, Y_BASE0),
        [(4, Y_MID0), (8, Y_MID0), (12, Y_MID1), (8, Y_MID1)],  # knee step
    ]),

    "l": GlyphDef(12, [
        R(0, Y_CAP0, 4,  Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # m = double n (width 20)
    "m": GlyphDef(20, [
        R(0, Y_TOP0, 20, Y_TOP1),    # top bar across both humps
        R(0, Y_TOP0, 4,  Y_BASE1),   # left stem
        R(8, Y_TOP1, 12, Y_BASE1),   # middle stem (starts below top bar)
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
        [(0, Y_TOP0), (4, Y_TOP0), (8, Y_BASE0), (4, Y_BASE0)],
        [(8, Y_TOP0), (12, Y_TOP0), (8, Y_BASE0), (4, Y_BASE0)],
        R(4, Y_BASE0, 8,  Y_BASE1),
    ]),

    # w = double u (width 20)
    "w": GlyphDef(20, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(16, Y_TOP0, 20, Y_BASE1),
        R(0, Y_BASE0, 20, Y_BASE1),
    ]),

    # x: placeholder (we’ll refine later)
    "x": GlyphDef(12, [
        [(0, Y_TOP0), (4, Y_TOP0), (12, Y_BASE0), (8, Y_BASE0)],
        [(8, Y_TOP0), (12, Y_TOP0), (4, Y_BASE0), (0, Y_BASE0)],
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


def compose_ligature_spaced_with_link(
    left_key: str,
    right_key: str,
    *,
    gap: int = 4,
    link_y0: int = Y_TOP0,
    link_y1: int = Y_TOP1,
    link_into_glyph: int = 1,
) -> GlyphDef:
    """
    Spacious ligature: keep a gap (like your monogram spacing),
    and connect them with a thin (1-unit) horizontal link line.

    link_into_glyph controls how far the connector reaches *into* each glyph.
    """
    left = GLYPHS[left_key]
    right = GLYPHS[right_key]

    dx = left.width + gap
    width = left.width + gap + right.width

    polys = list(left.polys) + [translate_poly(p, dx, 0) for p in right.polys]

    x0 = max(0, left.width - link_into_glyph)
    x1 = min(width, left.width + gap + link_into_glyph)
    polys.append(R(x0, link_y0, x1, link_y1))

    return GlyphDef(width, polys)


# Custom 'st' from your original sample, normalized to x=0..24
ST_POLY: Poly = [
    (24,10),(24,9),(20,9),(20,0),(11,0),(11,9),(0,9),(0,15),(8,15),(8,19),(0,19),(0,20),
    (12,20),(12,14),(4,14),(4,10),(12,10),(12,1),(16,1),(16,20),(24,20),(24,19),(20,19),(20,10)
]
GLYPHS["st"] = GlyphDef(24, [ST_POLY])

# Tight overlap ligatures
GLYPHS["fi"] = compose_ligature_overlap("f", "i", overlap=4)
GLYPHS["ij"] = compose_ligature_overlap("i", "j", overlap=4)

# Spaced ligatures with thin connector (more like 'st' vibe)
GLYPHS["ch"] = compose_ligature_spaced_with_link("c", "h", gap=4, link_y0=Y_TOP0, link_y1=Y_TOP1, link_into_glyph=1)
GLYPHS["sh"] = compose_ligature_spaced_with_link("s", "h", gap=4, link_y0=Y_TOP0, link_y1=Y_TOP1, link_into_glyph=1)
# For 'ct', reach into the 't' far enough to touch its stem at x=4..8
GLYPHS["ct"] = compose_ligature_spaced_with_link("c", "t", gap=4, link_y0=Y_TOP0, link_y1=Y_TOP1, link_into_glyph=4)

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
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" shape-rendering="crispEdges">\n'
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
