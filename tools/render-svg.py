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

# Common viewBox HEIGHT for *all* letters (includes ascenders + descenders)
# Baseline is at y=20; x-height starts at y=9; cap starts at y=0.
# Ascender height above x-height = 9 units (0..9), so descender depth below baseline = 9 units (20..29),
# plus the same 1-unit bar thickness => bottom reaches y=30.
CELL_H = 30

# Key y lines (all horizontal strokes are 1 unit thick)
Y_CAP0,  Y_CAP1  = 0, 1
Y_TOP0,  Y_TOP1  = 9, 10
Y_MID0,  Y_MID1  = 14, 15
Y_BASE0, Y_BASE1 = 19, 20
Y_DESC0, Y_DESC1 = 29, 30  # descender “bottom line” thickness (if needed)


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
# Simple transforms on polygons
# -----------------------------
def rotate180_poly(poly: Poly, w: int, cy2: int) -> Poly:
    """
    180° rotation around (w/2, cy2/2).
    For the lowercase band center: cy2 = Y_TOP0 + Y_BASE1 = 29 (since center y=14.5).
    """
    return [(w - x, cy2 - y) for (x, y) in poly]


def mirrorx_poly(poly: Poly, w: int) -> Poly:
    """Mirror around vertical centerline x=w/2."""
    return [(w - x, y) for (x, y) in poly]


# -----------------------------
# Canonical “s” from your sample (cut loose from the ST monogram)
# This is the exact stepped outline implied by your ST polygon’s S-part.
# (12×20 lowercase band: y=9..20)
# -----------------------------
S_POLY: Poly = [
    (0, 9),
    (12, 9),
    (12, 10),
    (8, 10),
    (8, 14),
    (4, 14),
    (4, 15),
    (0, 15),
    (0, 20),
    (12, 20),
    (12, 19),
    (8, 19),
    (8, 15),
    (12, 15),
    (12, 10),
    (12, 9),
]


# -----------------------------
# Glyphs
# Notes applied:
# - a = e rotated 180° (in the lowercase band)
# - descenders go as far below baseline as ascenders go above x-height (so down to y=30)
# - s is now the exact sample S shape (standalone)
# - z = mirrored s
# - p/q/y/j updated for new descender depth
# -----------------------------
GLYPHS: Dict[str, GlyphDef] = {}

# --- base e (used to derive a) ---
E_DEF = GlyphDef(12, [
    R(0, Y_TOP0, 12, Y_TOP1),        # top bar
    R(0, Y_TOP1, 4, Y_BASE0),        # left stem down
    R(8, Y_TOP1, 12, Y_MID0),        # upper-right closure (loop)
    R(0, Y_MID0, 12, Y_MID1),        # mid bar
    R(0, Y_BASE0, 12, Y_BASE1),      # baseline
])

# a = e rotated 180° around lowercase band center (x=6, y=14.5 => cy2=29)
A_DEF = GlyphDef(12, [
    rotate180_poly(p, 12, Y_TOP0 + Y_BASE1) for p in E_DEF.polys
])

# s = exact sample S shape
# --- replace your current S_DEF / Z_DEF with these ---

S_DEF = GlyphDef(12, [
    R(0, Y_TOP0, 12, Y_TOP1),        # top bar:  y=9..10
    R(0, Y_TOP1, 4,  Y_MID0),        # left vertical: y=10..14
    R(0, Y_MID0, 12, Y_MID1),        # mid bar:  y=14..15
    R(8, Y_MID1, 12, Y_BASE0),       # right vertical: y=15..19
    R(0, Y_BASE0, 12, Y_BASE1),      # bottom bar: y=19..20
])

Z_DEF = GlyphDef(12, [
    R(0, Y_TOP0, 12, Y_TOP1),        # top bar
    R(8, Y_TOP1, 12, Y_MID0),        # right vertical (mirrored)
    R(0, Y_MID0, 12, Y_MID1),        # mid bar
    R(0, Y_MID1, 4,  Y_BASE0),       # left vertical (mirrored)
    R(0, Y_BASE0, 12, Y_BASE1),      # bottom bar
])

# Fill glyph table (everything except g/x final forms, per your note)
GLYPHS.update({
    "a": A_DEF,

    "b": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE1),        # tall left stem
        R(4, Y_TOP0, 12, Y_TOP1),        # bowl top
        R(8, Y_TOP1, 12, Y_BASE0),       # bowl right
        R(4, Y_BASE0, 12, Y_BASE1),      # bowl bottom
    ]),

    "c": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "d": GlyphDef(12, [
        R(8, Y_CAP0, 12, Y_BASE1),
        R(0, Y_TOP0, 8, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(0, Y_BASE0, 8, Y_BASE1),
    ]),

    "e": E_DEF,

    "f": GlyphDef(12, [
        R(4, Y_CAP0, 8, Y_BASE1),        # main stem
        R(4, Y_CAP0, 12, Y_CAP1),        # cap bar (to the right)
        R(4, Y_TOP0, 12, Y_TOP1),        # x-height bar (to the right)
    ]),

    # g: placeholder for now (we’ll revisit)
    "g": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "h": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ]),

    "i": GlyphDef(12, [
        R(4, Y_TOP0, 8, Y_BASE1),        # stem
        R(4, 0, 8, 4),                   # square dot
    ]),

    "j": GlyphDef(12, [
        R(4, Y_TOP0, 8, Y_DESC1),        # stem with descender
        R(4, 0, 8, 4),                   # square dot
        R(0, Y_DESC0, 4, Y_DESC1),       # thin hook to the left only
    ]),

    "k": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(4, Y_TOP1, 12, Y_MID0),
        R(4, Y_MID1, 12, Y_BASE0),
        [(4, Y_MID0), (8, Y_MID0), (12, Y_MID1), (8, Y_MID1)],  # tiny knee step
    ]),

    "l": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # m = double n (width 20, overlap rhythm like your monogram spacing)
    "m": GlyphDef(20, [
        R(0, Y_TOP0, 20, Y_TOP1),        # top bar across both humps
        R(0, Y_TOP0, 4, Y_BASE1),        # left stem
        R(8, Y_TOP1, 12, Y_BASE1),       # middle stem (starts below top bar)
        R(16, Y_TOP1, 20, Y_BASE1),      # right stem
    ]),

    "n": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ]),

    "o": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # p = like o, but left stem descends (same “amount” as h ascends)
    "p": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),        # top bar
        R(0, Y_TOP1, 4, Y_DESC1),        # left stem descender
        R(8, Y_TOP1, 12, Y_BASE0),       # right bowl wall (only in bowl zone)
        R(0, Y_BASE0, 12, Y_BASE1),      # baseline bar
    ]),

    # q = mirror of p
    "q": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(8, Y_TOP1, 12, Y_DESC1),       # right stem descender
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # r = only stem + top horizontal line
    "r": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
    ]),

    "s": S_DEF,

    "t": GlyphDef(12, [
        R(4, Y_CAP0, 8, Y_BASE1),        # stem
        R(8, Y_TOP0, 12, Y_TOP1),        # x-height bar to the right
        R(8, Y_BASE0, 12, Y_BASE1),      # baseline bar to the right
    ]),

    "u": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "v": GlyphDef(12, [
        [(0, Y_TOP0), (4, Y_TOP0), (8, Y_BASE0), (4, Y_BASE0)],
        [(8, Y_TOP0), (12, Y_TOP0), (8, Y_BASE0), (4, Y_BASE0)],
        R(4, Y_BASE0, 8, Y_BASE1),
    ]),

    # w = double u (width 20)
    "w": GlyphDef(20, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(16, Y_TOP0, 20, Y_BASE1),
        R(0, Y_BASE0, 20, Y_BASE1),
    ]),

    # x: placeholder for now (we’ll revisit)
    "x": GlyphDef(12, [
        [(0, Y_TOP0), (4, Y_TOP0), (12, Y_BASE0), (8, Y_BASE0)],
        [(8, Y_TOP0), (12, Y_TOP0), (4, Y_BASE0), (0, Y_BASE0)],
        R(4, Y_MID0, 8, Y_MID1),
    ]),

    # y = u with a descender stem (right side descends)
    "y": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP0, 12, Y_DESC1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "z": Z_DEF,
})


# -----------------------------
# SVG rendering / writing
# -----------------------------
def render_glyph_svg(letter: str, g: GlyphDef) -> str:
    vb = f"0 0 {g.width} {CELL_H}"  # same height for every file
    polys = "\n".join(
        f'    <polygon class="{letter}" points="{poly_points(poly)}"/>'
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
    """
    Script lives in a subfolder (e.g. ./tools/ or ./scripts/),
    so project root is exactly ONE directory above this file.
    Works regardless of where you run it from.
    """
    return Path(__file__).resolve().parent.parent

def write_all_lowercase_svgs(out_dir_rel: str = "sketches") -> None:
    root = project_root()
    out_dir = root / out_dir_rel
    out_dir.mkdir(parents=True, exist_ok=True)

    for letter in "abcdefghijklmnopqrstuvwxyz":
        g = GLYPHS.get(letter)
        if not g:
            raise KeyError(f"Missing glyph: {letter}")

        svg = render_glyph_svg(letter, g)
        (out_dir / f"{letter}.svg").write_text(svg, encoding="utf-8")

    print(f"Wrote 26 SVGs to: {out_dir}")

if __name__ == "__main__":
    write_all_lowercase_svgs("sketches")
