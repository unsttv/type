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

# Common viewBox HEIGHT for *all* letters (includes descenders)
# Baseline remains at y=20; descenders can go to y=24.
CELL_H = 24

# Horizontal bar thickness is always 1
Y_CAP0, Y_CAP1 = 0, 1
Y_TOP0, Y_TOP1 = 9, 10
Y_MID0, Y_MID1 = 14, 15
Y_BASE0, Y_BASE1 = 19, 20
Y_DESC0, Y_DESC1 = 23, 24  # thin bottom line location if needed


def R(x1: int, y1: int, x2: int, y2: int) -> Poly:
    """Axis-aligned rectangle as a polygon (clockwise)."""
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def SL(x1_top: int, x2_top: int, y_top: int, x1_bot: int, x2_bot: int, y_bot: int) -> Poly:
    """4-pt slanted bar (trapezoid/parallelogram) from y_top to y_bot."""
    return [(x1_top, y_top), (x2_top, y_top), (x2_bot, y_bot), (x1_bot, y_bot)]


@dataclass(frozen=True)
class GlyphDef:
    width: int
    polys: List[Poly]


# -----------------------------
# Glyphs (updated per your notes)
# -----------------------------
GLYPHS: Dict[str, GlyphDef] = {
    # a: rebuilt using the (fixed) s + u logic (open on top-left, bowl on bottom)
    "a": GlyphDef(12, [
        # right stem
        R(8, Y_TOP0, 12, Y_BASE1),
        # top (partial) + upper-right block like the sample S logic
        R(4, Y_TOP0, 12, Y_TOP1),
        R(4, Y_TOP1, 12, Y_MID0),
        R(4, Y_MID0, 12, Y_MID1),
        # lower-left bowl like the sample S lower block
        R(0, Y_MID1, 8, Y_BASE0),
        # baseline
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # b: remove the middle horizontal line (keep bowl + stem)
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

    # e: close the *top half* on the right side (upper loop)
    "e": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),        # top bar
        R(0, Y_TOP1, 4, Y_BASE0),        # left stem down
        R(8, Y_TOP1, 12, Y_MID0),        # upper right closure (loop)
        R(0, Y_MID0, 12, Y_MID1),        # mid bar
        R(0, Y_BASE0, 12, Y_BASE1),      # baseline
    ]),

    # f: horizontal lines extend to the right from the stem
    "f": GlyphDef(12, [
        R(4, Y_CAP0, 8, Y_BASE1),        # main stem
        R(4, Y_CAP0, 12, Y_CAP1),        # cap bar (right)
        R(4, Y_TOP0, 12, Y_TOP1),        # x-height bar (right)
    ]),

    # g: placeholder (we’ll revisit later)
    "g": GlyphDef(12, [
        # for now: same as "o"
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

    # i: dot thicker (square)
    "i": GlyphDef(12, [
        R(4, Y_TOP0, 8, Y_BASE1),        # stem
        R(4, 0, 8, 4),                   # square dot
    ]),

    # j: thicker dot + descender + thin leftward hook
    "j": GlyphDef(12, [
        R(4, Y_TOP0, 8, Y_DESC1),        # stem with descender
        R(4, 0, 8, 4),                   # square dot
        R(0, Y_DESC0, 8, Y_DESC1),       # thin hook to the left (and under stem)
    ]),

    "k": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(4, Y_TOP1, 12, Y_MID0),
        R(4, Y_MID1, 12, Y_BASE0),
        SL(4, 8, Y_MID0, 8, 12, Y_MID1),
    ]),

    "l": GlyphDef(12, [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # m: basically a double "n" (overlapped by 8 → 20 wide with shared middle stem)
    "m": GlyphDef(20, [
        R(0, Y_TOP0, 20, Y_TOP1),        # top bar across both humps
        R(0, Y_TOP0, 4, Y_BASE1),        # left stem
        R(8, Y_TOP1, 12, Y_BASE1),       # shared middle stem (starts below top bar)
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

    # p: like "o" but with a stem going below the baseline (descender on left)
    "p": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),        # top bar
        R(0, Y_TOP1, 4, Y_DESC1),        # left stem descender
        R(8, Y_TOP1, 12, Y_BASE0),       # right of bowl (only within x-height band)
        R(0, Y_BASE0, 12, Y_BASE1),      # baseline bar
    ]),

    # q: mirror of p (descender on right)
    "q": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(8, Y_TOP1, 12, Y_DESC1),       # right stem descender
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    # r: only stem + top horizontal line
    "r": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
    ]),

    # s: closer to your sample (no diagonal join; 8-wide blocks + full top/bottom)
    "s": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),        # top bar
        R(4, Y_TOP1, 12, Y_MID0),        # upper right block (8 wide)
        R(4, Y_MID0, 12, Y_MID1),        # mid bar (right, 8 wide)
        R(0, Y_MID1, 8, Y_BASE0),        # lower left block (8 wide)
        R(0, Y_BASE0, 12, Y_BASE1),      # bottom bar
    ]),

    # t: only stem + middle line to the right
    "t": GlyphDef(12, [
        R(4, Y_CAP0, 8, Y_BASE1),        # stem
        R(8, Y_MID0, 12, Y_MID1),        # mid line to the right
    ]),

    "u": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ]),

    "v": GlyphDef(12, [
        SL(0, 4, Y_TOP0, 4, 8, Y_BASE0),
        SL(8, 12, Y_TOP0, 4, 8, Y_BASE0),
        R(4, Y_BASE0, 8, Y_BASE1),
    ]),

    # w: basically a double "u" (overlapped by 8 → 20 wide with shared middle stem)
    "w": GlyphDef(20, [
        R(0, Y_TOP0, 4, Y_BASE1),        # left stem
        R(8, Y_TOP0, 12, Y_BASE1),       # shared middle stem
        R(16, Y_TOP0, 20, Y_BASE1),      # right stem
        R(0, Y_BASE0, 20, Y_BASE1),      # baseline
    ]),

    # x: placeholder (we’ll revisit later)
    "x": GlyphDef(12, [
        SL(0, 4, Y_TOP0, 8, 12, Y_BASE0),
        SL(8, 12, Y_TOP0, 0, 4, Y_BASE0),
        R(4, Y_MID0, 8, Y_MID1),
    ]),

    # y: a "u" with a stem below the baseline (descender on right)
    "y": GlyphDef(12, [
        R(0, Y_TOP0, 4, Y_BASE1),        # left stem
        R(8, Y_TOP0, 12, Y_DESC1),       # right stem descender
        R(0, Y_BASE0, 12, Y_BASE1),      # baseline
    ]),

    # z: same as s (after fixes) but mirrored
    "z": GlyphDef(12, [
        R(0, Y_TOP0, 12, Y_TOP1),        # top bar
        R(0, Y_TOP1, 8, Y_MID0),         # upper left block (8 wide)
        R(0, Y_MID0, 8, Y_MID1),         # mid bar (left, 8 wide)
        R(4, Y_MID1, 12, Y_BASE0),       # lower right block (8 wide)
        R(0, Y_BASE0, 12, Y_BASE1),      # bottom bar
    ]),
}


def poly_points(poly: Poly) -> str:
    return " ".join(f"{x},{y}" for x, y in poly)


def render_glyph_svg(letter: str, g: GlyphDef) -> str:
    vb = f"0 0 {g.width} {CELL_H}"
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


def project_root_one_up() -> Path:
    """
    You said: assume the script is run from a subfolder.
    So we treat the project root as: (this file's folder) / ..
    """
    try:
        return Path(__file__).resolve().parent.parent
    except NameError:
        # fallback for interactive use
        return Path.cwd().resolve().parent


def write_all_lowercase_svgs(out_dir_rel: str = "sketches") -> None:
    root = project_root_one_up()
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
