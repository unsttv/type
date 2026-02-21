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

    "f": GlyphDef(8, [
        R(0, Y_CAP0, 4,  Y_BASE1),   # main stem
        R(0, Y_CAP0, 8,  Y_CAP1),    # cap bar
        R(0, Y_TOP0, 8,  Y_TOP1),    # x-height bar
    ]),

    # FIXED g: move the lower-loop top bar from 20..21 to 19..20 (baseline band),
    # and start the lower-loop side stems at y=20 so the loop stays closed.
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

        # Row 5: xxx  (NOW baseline band 19..20)
        R(0, Y_BASE0, 12, Y_BASE1),

        # Row 6: xox  (start at 20 now, so it touches the bar)
        R(0, Y_BASE1, 4,  Y_BASE1 + 5),
        R(8, Y_BASE1, 12, Y_BASE1 + 5),

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

    "i": GlyphDef(4, [
        R(0, Y_TOP0, 4,  Y_BASE1),   # stem
        R(0, 0,      4,  4),         # square dot
    ]),

    "j": GlyphDef(8, [
        R(4, Y_TOP0, 8,  Y_DESC1),   # stem with descender
        R(4, 0,      8,  4),         # square dot
        R(0, Y_DESC0, 4,  Y_DESC1),  # thin hook to the left
    ]),

    "k": GlyphDef(12, [
        R(0, Y_CAP0, 4,  Y_BASE1),      # main stem |

        # right bar split (gap at mid band)
        R(8, Y_TOP0, 12, Y_MID0),       # upper right |
        R(8, Y_MID1, 12, Y_BASE1),      # lower right |

        # mid connector ONLY between stem and right bar boundary
        R(4, Y_MID0, 8,  Y_MID1),
    ]),

    "l": GlyphDef(8, [
        R(0, Y_CAP0, 4,  Y_BASE1),
        R(0, Y_BASE0, 8,  Y_BASE1),
    ]),

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

    "p": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_DESC1),   # descender
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "q": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4,  Y_BASE0),
        R(8, Y_TOP1, 12, Y_DESC1),   # descender
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "r": GlyphDef(8, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(0, Y_TOP0, 8,  Y_TOP1),
    ]),

    "s": S_DEF,

    "t": GlyphDef(8, [
        R(0, Y_CAP0, 4,  Y_BASE1),   # stem
        R(4, Y_TOP0, 8,  Y_TOP1),    # x-height bar right
        R(4, Y_BASE0, 8,  Y_BASE1),  # baseline bar right
    ]),

    "u": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "v": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_MID1),
        R(8, Y_TOP0, 12, Y_MID1),
        R(0, Y_MID0, 12, Y_MID1),
        R(4, Y_MID1, 8,  Y_BASE1),
    ]),

    "w": GlyphDef(20, [
        R(0, Y_TOP0, 4,  Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(16, Y_TOP0, 20, Y_BASE1),
        R(0, Y_BASE0, 20, Y_BASE1),
    ]),

    "x": GlyphDef(12, [
        R(0, Y_TOP0, 4,  Y_MID0),
        R(0, Y_MID1, 4,  Y_BASE1),

        R(8, Y_TOP0, 12, Y_MID0),
        R(8, Y_MID1, 12, Y_BASE1),

        R(4, Y_MID0, 8,  Y_MID1),
    ]),

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
    "1": GlyphDef(8, [
        R(0, Y_TOP0, 8,  Y_TOP1),
        R(4, Y_TOP1, 8,  Y_BASE1),
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
# Capital letters A–Z (same rectangle/band logic)
# Cap zone is y=0..20 (cap band 0..1, baseline band 19..20).
# -----------------------------
def cap_stem_left() -> Poly:
    return R(0, Y_CAP0, 4, Y_BASE1)

def cap_stem_right() -> Poly:
    return R(8, Y_CAP0, 12, Y_BASE1)

def cap_top_bar() -> Poly:
    return R(0, Y_CAP0, 12, Y_CAP1)

def cap_bottom_bar() -> Poly:
    return R(0, Y_BASE0, 12, Y_BASE1)

def cap_mid_bar() -> Poly:
    return R(0, Y_MID0, 12, Y_MID1)

def diag_steps_5_down_right(x0: int, y0: int, w: int = 4) -> List[Poly]:
    """5-step staircase diagonal from top-left to bottom-right within 0..20."""
    # y slices: 0..4, 4..8, 8..12, 12..16, 16..20
    ys = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20)]
    xs = [(x0 + 0, x0 + 0 + w),
          (x0 + 2, x0 + 2 + w),
          (x0 + 4, x0 + 4 + w),
          (x0 + 6, x0 + 6 + w),
          (x0 + 8, x0 + 8 + w)]
    return [R(xa, ya, xb, yb) for (xa, xb), (ya, yb) in zip(xs, ys)]

def diag_steps_5_down_left(x0: int, y0: int, w: int = 4) -> List[Poly]:
    """5-step staircase diagonal from top-right to bottom-left within 0..20."""
    ys = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20)]
    xs = [(x0 + 8, x0 + 8 + w),
          (x0 + 6, x0 + 6 + w),
          (x0 + 4, x0 + 4 + w),
          (x0 + 2, x0 + 2 + w),
          (x0 + 0, x0 + 0 + w)]
    return [R(xa, ya, xb, yb) for (xa, xb), (ya, yb) in zip(xs, ys)]

GLYPHS.update({
    "A": GlyphDef(12, [
        cap_stem_left(),
        cap_stem_right(),
        cap_top_bar(),
        cap_mid_bar(),
    ]),

    "B": GlyphDef(12, [
        cap_stem_left(),
        cap_top_bar(),
        cap_mid_bar(),
        cap_bottom_bar(),
        R(8, Y_CAP1, 12, Y_MID0),  # upper right
        R(8, Y_MID1, 12, Y_BASE0), # lower right
    ]),

    "C": GlyphDef(12, [
        cap_top_bar(),
        R(0, Y_CAP1, 4, Y_BASE0),
        cap_bottom_bar(),
    ]),

    # D differs from O by leaving the top-right & bottom-right corners "open":
    # right stem starts at y=1 and ends at y=19 (no pixels in the 0..1 and 19..20 bands).
    "D": GlyphDef(12, [
        cap_stem_left(),
        R(0, Y_CAP0, 8, Y_CAP1),         # top bar stops at x=8
        R(0, Y_BASE0, 8, Y_BASE1),       # bottom bar stops at x=8
        R(8, Y_CAP1, 12, Y_BASE0),       # right vertical (no corners)
    ]),

    "E": GlyphDef(12, [
        cap_stem_left(),
        cap_top_bar(),
        cap_mid_bar(),
        cap_bottom_bar(),
    ]),

    "F": GlyphDef(12, [
        cap_stem_left(),
        cap_top_bar(),
        cap_mid_bar(),
    ]),

    "G": GlyphDef(12, [
        cap_top_bar(),
        R(0, Y_CAP1, 4, Y_BASE0),
        cap_bottom_bar(),
        R(8, Y_MID1, 12, Y_BASE1),       # right lower
        R(4, Y_MID0, 12, Y_MID1),        # inward mid bar
    ]),

    "H": GlyphDef(12, [
        cap_stem_left(),
        cap_stem_right(),
        cap_mid_bar(),
    ]),

    "I": GlyphDef(12, [
        cap_top_bar(),
        R(4, Y_CAP1, 8, Y_BASE0),        # center stem
        cap_bottom_bar(),
    ]),

    "J": GlyphDef(12, [
        cap_top_bar(),
        R(8, Y_CAP1, 12, Y_BASE0),       # right stem
        cap_bottom_bar(),
        R(0, 15, 4, Y_BASE0),            # left hook up
    ]),

    "K": GlyphDef(12, [
        cap_stem_left(),
        R(8, Y_CAP0, 12, Y_MID0),        # upper right
        R(8, Y_MID1, 12, Y_BASE1),       # lower right
        cap_mid_bar(),                    # mid connector across
        R(4, Y_MID0, 8, Y_MID1),         # reinforce connector thickness
    ]),

    "L": GlyphDef(12, [
        cap_stem_left(),
        cap_bottom_bar(),
    ]),

    "M": GlyphDef(20, [
        R(0,  Y_CAP0, 4,  Y_BASE1),      # left stem
        R(8,  Y_CAP0, 12, Y_BASE1),      # middle stem
        R(16, Y_CAP0, 20, Y_BASE1),      # right stem
        R(0,  Y_CAP0, 20, Y_CAP1),       # cap bar (ties it together)
    ]),

    "N": GlyphDef(12, [
        cap_stem_left(),
        cap_stem_right(),
        R(4, 0,  8,  5),
        R(5, 5,  9, 10),
        R(6, 10, 10, 15),
        R(7, 15, 11, 20),
    ]),

    "O": GlyphDef(12, [
        cap_top_bar(),
        R(0, Y_CAP1, 4, Y_BASE0),
        R(8, Y_CAP1, 12, Y_BASE0),
        cap_bottom_bar(),
    ]),

    "P": GlyphDef(12, [
        cap_stem_left(),
        cap_top_bar(),
        cap_mid_bar(),
        R(8, Y_CAP1, 12, Y_MID0),        # upper right
    ]),

    "Q": GlyphDef(12, [
        cap_top_bar(),
        R(0, Y_CAP1, 4, Y_BASE0),
        R(8, Y_CAP1, 12, Y_BASE0),
        cap_bottom_bar(),
        R(8, 20, 12, 24),                # small tail below baseline
    ]),

    "R": GlyphDef(12, [
        cap_stem_left(),
        cap_top_bar(),
        cap_mid_bar(),
        R(8, Y_CAP1, 12, Y_MID0),        # upper right (like P)
        R(8, Y_MID1, 12, Y_BASE1),       # leg down
    ]),

    "S": GlyphDef(12, [
        cap_top_bar(),
        R(0, Y_CAP1, 4, Y_MID0),         # upper-left
        cap_mid_bar(),
        R(8, Y_MID1, 12, Y_BASE0),       # lower-right
        cap_bottom_bar(),
    ]),

    "T": GlyphDef(12, [
        cap_top_bar(),
        R(4, Y_CAP1, 8, Y_BASE1),        # center stem
    ]),

    "U": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE0),        # left stem (no bottom band)
        R(8, Y_CAP0, 12, Y_BASE0),       # right stem
        cap_bottom_bar(),
    ]),

    "V": GlyphDef(12, [
        R(0, 0, 4, 5),
        R(1, 5, 5, 10),
        R(2, 10, 6, 15),
        R(3, 15, 7, 19),

        R(8, 0, 12, 5),
        R(7, 5, 11, 10),
        R(6, 10, 10, 15),
        R(5, 15, 9, 19),

        R(4, Y_BASE0, 8, Y_BASE1),       # point
    ]),

    "W": GlyphDef(20, [
        R(0,  Y_CAP0, 4,  Y_BASE0),
        R(8,  Y_CAP0, 12, Y_BASE0),
        R(16, Y_CAP0, 20, Y_BASE0),
        R(0,  Y_BASE0, 20, Y_BASE1),     # baseline
    ]),

    "X": GlyphDef(12, [
        *diag_steps_5_down_right(0, 0, 4),
        *diag_steps_5_down_left(0, 0, 4),
    ]),

    "Y": GlyphDef(12, [
        R(0, 0, 4, 5),
        R(2, 5, 6, 10),

        R(8, 0, 12, 5),
        R(6, 5, 10, 10),

        R(4, 10, 8, 20),                 # stem down
    ]),

    "Z": GlyphDef(12, [
        cap_top_bar(),
        cap_bottom_bar(),
        R(8, 1, 12, 5),
        R(6, 5, 10, 9),
        R(4, 9, 8, 13),
        R(2, 13, 6, 17),
        R(0, 17, 4, 19),
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
      - start at x-height (y=Y_TOP1 == 10)
      - go UP to the ascender top (y=0..1 band)
      - then go RIGHT along that top band into the right glyph
    """
    left = GLYPHS[left_key]
    right = GLYPHS[right_key]

    dx = left.width + gap
    width = left.width + gap + right.width

    polys = list(left.polys) + [translate_poly(p, dx, 0) for p in right.polys]

    x0 = left.width - 1
    x1 = left.width

    polys.append(R(x0, Y_LINK0, x1, Y_TOP1))  # vertical
    h_x0 = x0
    h_x1 = dx + max(1, right_touch_x)
    polys.append(R(h_x0, Y_LINK0, h_x1, Y_LINK1))  # horizontal (top band)

    return GlyphDef(width, polys)


def ligature_bottom_like(left_key: str, right_key: str, *, gap: int = 4, right_touch_x: int = 1) -> GlyphDef:
    """
    Bottom-connected ligature:
      - keep a normal gap
      - extend the BASELINE band (19..20) across the gap into the right glyph
    This keeps the connection in a canonical 1-unit band.
    """
    left = GLYPHS[left_key]
    right = GLYPHS[right_key]

    dx = left.width + gap
    width = left.width + gap + right.width

    polys = list(left.polys) + [translate_poly(p, dx, 0) for p in right.polys]

    # extend baseline band across the gap
    x0 = left.width - 1
    x1 = dx + max(1, right_touch_x)
    polys.append(R(x0, Y_BASE0, x1, Y_BASE1))

    return GlyphDef(width, polys)


def ligature_bottom_desc_like(left_key: str, right_key: str, *, gap: int = 4, right_touch_x: int = 1) -> GlyphDef:
    """
    Bottom-connected ligature at the *descender bottom* (29..30 band), not baseline.
    Useful for ligatures like 'yp' where the visual connection should be at the very bottom.
    """
    left = GLYPHS[left_key]
    right = GLYPHS[right_key]

    dx = left.width + gap
    width = left.width + gap + right.width

    polys = list(left.polys) + [translate_poly(p, dx, 0) for p in right.polys]

    # extend bottom-most thin band across the gap
    x0 = left.width - 1
    x1 = dx + max(1, right_touch_x)
    polys.append(R(x0, Y_DESC0, x1, Y_DESC1))

    return GlyphDef(width, polys)


# (kept for reference; not used)
ST_POLY: Poly = [
    (24,10),(24,9),(20,9),(20,0),(11,0),(11,9),(0,9),(0,15),(8,15),(8,19),(0,19),(0,20),
    (12,20),(12,14),(4,14),(4,10),(12,10),(12,1),(16,1),(16,20),(24,20),(24,19),(20,19),(20,10)
]

# st (st-like, as per your current setup)
GLYPHS["st"] = ligature_st_like("s", "t", gap=4, right_touch_x=4)

# Tight overlap ligatures
GLYPHS["fi"] = compose_ligature_overlap("f", "i", overlap=0)
GLYPHS["ij"] = compose_ligature_overlap("i", "j", overlap=0)

# st-like ligatures
GLYPHS["ch"] = ligature_st_like("c", "h", gap=4, right_touch_x=1)
GLYPHS["sh"] = ligature_st_like("s", "h", gap=4, right_touch_x=1)
GLYPHS["ct"] = ligature_st_like("c", "t", gap=4, right_touch_x=4)

# NEW bottom-connected ligatures
GLYPHS["es"] = ligature_bottom_like("e", "s", gap=4, right_touch_x=1)
GLYPHS["yp"] = ligature_bottom_desc_like("y", "p", gap=4, right_touch_x=1)

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
        f'viewBox="{vb}" width="{g.width}" height="{CELL_H}" '
        'shape-rendering="crispEdges">\n'
        "  <g>\n"
        f"{polys}\n"
        "  </g>\n"
        "</svg>\n"
    )


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def codepoint_hex(ch: str) -> str:
    """Lowercase hex Unicode codepoint, minimum 4 digits."""
    return f"{ord(ch):04x}"


def filename_for_glyph_key(key: str) -> str:
    """
    Single codepoint glyphs:
      character-uXXXX.svg
    Ligatures / multi-codepoint glyphs:
      ligature-uXXXX-uYYYY.svg
    """
    if len(key) == 1:
        return f"character-u{codepoint_hex(key)}.svg"

    cps = "-".join(f"u{codepoint_hex(ch)}" for ch in key)
    return f"ligature-{cps}.svg"


def export_keys() -> List[str]:
    """
    Export all standard single-codepoint glyphs in a predictable order,
    then any multi-character glyph keys (ligatures) that exist in GLYPHS.
    """
    singles = (
        list("abcdefghijklmnopqrstuvwxyz")
        + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        + list("0123456789")
    )

    # Automatically include all ligatures / multi-character glyphs present
    ligatures = sorted([k for k in GLYPHS.keys() if len(k) > 1])

    return singles + ligatures


def write_all_svgs() -> None:
    root = project_root()
    out_dir = root / "src"
    out_dir.mkdir(parents=True, exist_ok=True)

    keys = export_keys()

    for key in keys:
        g = GLYPHS.get(key)
        if not g:
            raise KeyError(f"Missing glyph: {key}")

        svg = render_glyph_svg(key, g)
        fname = filename_for_glyph_key(key)
        (out_dir / fname).write_text(svg, encoding="utf-8")

    n_single = sum(1 for k in keys if len(k) == 1)
    n_liga = sum(1 for k in keys if len(k) > 1)
    print(f"Wrote {len(keys)} SVGs to: {out_dir} ({n_single} single glyphs, {n_liga} ligatures)")


if __name__ == "__main__":
    write_all_svgs()
