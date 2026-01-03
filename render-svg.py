from __future__ import annotations
from typing import Dict, List, Tuple
from pathlib import Path

Point = Tuple[int, int]
Poly = List[Point]
Glyph = List[Poly]

CELL_W, CELL_H = 12, 20
ADVANCE = 16  # 12 width + 4 tracking, like your sample

# Key y lines
Y_CAP0, Y_CAP1 = 0, 1
Y_TOP0, Y_TOP1 = 9, 10
Y_MID0, Y_MID1 = 14, 15
Y_BASE0, Y_BASE1 = 19, 20


def R(x1: int, y1: int, x2: int, y2: int) -> Poly:
    """Axis-aligned rectangle as a polygon (clockwise)."""
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def SL(x1_top: int, x2_top: int, y_top: int, x1_bot: int, x2_bot: int, y_bot: int) -> Poly:
    """4-pt slanted bar (trapezoid/parallelogram) from y_top to y_bot."""
    return [(x1_top, y_top), (x2_top, y_top), (x2_bot, y_bot), (x1_bot, y_bot)]


GLYPHS: Dict[str, Glyph] = {
    "a": [
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
        R(4, Y_TOP0, 12, Y_TOP1),
        SL(4, 12, Y_MID0, 0, 8, Y_MID1),
        R(0, Y_MID1, 4, Y_BASE1),
    ],
    "b": [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(4, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(4, Y_MID0, 12, Y_MID1),
        R(4, Y_BASE0, 12, Y_BASE1),
    ],
    "c": [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ],
    "d": [
        R(8, Y_CAP0, 12, Y_BASE1),
        R(0, Y_TOP0, 8, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(0, Y_BASE0, 8, Y_BASE1),
    ],
    "e": [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(0, Y_MID0, 12, Y_MID1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ],
    "f": [
        R(4, Y_CAP0, 8, Y_BASE1),
        R(0, Y_CAP0, 12, Y_CAP1),
        R(0, Y_TOP0, 8, Y_TOP1),
    ],
    "g": [
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        SL(4, 12, Y_MID0, 0, 8, Y_MID1),
        R(0, Y_BASE0, 12, Y_BASE1),
        R(0, Y_MID1, 4, Y_BASE0),
        R(4, Y_MID1, 8, Y_BASE0),
    ],
    "h": [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ],
    "i": [
        R(4, Y_TOP0, 8, Y_BASE1),
        R(4, Y_CAP0, 8, Y_CAP1),
    ],
    "j": [
        R(4, Y_TOP0, 8, Y_BASE1),
        R(4, Y_CAP0, 8, Y_CAP1),
        R(0, Y_MID1, 4, Y_BASE1),
        R(0, Y_BASE0, 4, Y_BASE1),
    ],
    "k": [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(4, Y_TOP1, 12, Y_MID0),
        R(4, Y_MID1, 12, Y_BASE0),
        SL(4, 8, Y_MID0, 8, 12, Y_MID1),
    ],
    "l": [
        R(0, Y_CAP0, 4, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ],
    "m": [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP1, 12, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(4, Y_TOP1, 8, Y_MID1),
    ],
    "n": [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_BASE1),
    ],
    "o": [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ],
    "p": [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_MID0),
        R(0, Y_MID0, 12, Y_MID1),
    ],
    "q": [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_TOP1, 4, Y_BASE0),
        R(8, Y_TOP1, 12, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
        SL(8, 12, Y_MID1, 4, 8, Y_BASE0),
    ],
    "r": [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_MID1),
        R(0, Y_MID0, 8, Y_MID1),
    ],
    "s": [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(8, Y_TOP1, 12, Y_MID0),
        SL(4, 12, Y_MID0, 0, 8, Y_MID1),
        R(0, Y_MID1, 4, Y_BASE0),
        R(0, Y_BASE0, 12, Y_BASE1),
    ],
    "t": [
        R(4, Y_CAP0, 8, Y_BASE1),
        R(0, Y_CAP0, 12, Y_CAP1),
        R(0, Y_TOP0, 12, Y_TOP1),
    ],
    "u": [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
    ],
    "v": [
        SL(0, 4, Y_TOP0, 4, 8, Y_BASE0),
        SL(8, 12, Y_TOP0, 4, 8, Y_BASE0),
        R(4, Y_BASE0, 8, Y_BASE1),
    ],
    "w": [
        R(0, Y_TOP0, 4, Y_BASE1),
        R(8, Y_TOP0, 12, Y_BASE1),
        R(0, Y_BASE0, 12, Y_BASE1),
        R(4, Y_MID1, 8, Y_BASE1),
    ],
    "x": [
        SL(0, 4, Y_TOP0, 8, 12, Y_BASE0),
        SL(8, 12, Y_TOP0, 0, 4, Y_BASE0),
        R(4, Y_MID0, 8, Y_MID1),
    ],
    "y": [
        SL(0, 4, Y_TOP0, 4, 8, Y_BASE0),
        SL(8, 12, Y_TOP0, 4, 8, Y_BASE0),
        R(4, Y_MID1, 8, Y_BASE1),
    ],
    "z": [
        R(0, Y_TOP0, 12, Y_TOP1),
        R(0, Y_BASE0, 12, Y_BASE1),
        SL(8, 12, Y_TOP1, 0, 4, Y_BASE0),
    ],
}


def poly_points(poly: Poly) -> str:
    return " ".join(f"{x},{y}" for x, y in poly)


def render_glyph_svg(letter: str, glyph: Glyph) -> str:
    # Same viewBox height for every file (0..20), even if a glyph doesn’t use cap area.
    vb = f"0 0 {CELL_W} {CELL_H}"
    polys = "\n".join(
        f'    <polygon class="{letter}" points="{poly_points(poly)}"/>'
        for poly in glyph
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" shape-rendering="crispEdges">\n'
        "  <g>\n"
        f"{polys}\n"
        "  </g>\n"
        "</svg>\n"
    )


def write_all_lowercase_svgs(out_dir: str | Path = "sketches") -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    for letter, glyph in sorted(GLYPHS.items()):
        svg = render_glyph_svg(letter, glyph)
        (out_path / f"{letter}.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    write_all_lowercase_svgs("sketches")
    print("Wrote: " + ", ".join(f"sketches/{c}.svg" for c in sorted(GLYPHS.keys())))
