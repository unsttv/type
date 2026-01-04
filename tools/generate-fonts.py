#!/usr/bin/env python3
"""
Build UNST font(s) from the SVG glyphs in ./src:

  src/character-a.svg
  ...
  src/character-0.svg
  ...
  src/character-st.svg
  src/character-ch.svg
  src/character-ct.svg
  src/character-fi.svg
  src/character-ij.svg
  src/character-sh.svg

Outputs (by default):
  dist/fonts/unst.ttf
  dist/fonts/unst.woff
  dist/fonts/unst.woff2   (if brotli is available)

Includes GSUB 'liga' substitutions for:
  st, ch, ct, fi, ij, sh

IMPORTANT (Option A seam-fix):
  This script unions/merges all polygons from each SVG into continuous outlines
  (with proper holes) BEFORE building the glyph. This reduces internal edges and
  helps prevent tiny seams/gaps under rasterization/interpolation.

Requires:
  pip install fonttools shapely

Optional for woff2:
  pip install brotli
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

try:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
except Exception as e:
    raise SystemExit("fontTools.feaLib is required (it ships with fonttools).") from e

# Option A union/merge
try:
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.ops import unary_union
except Exception as e:
    raise SystemExit("This script requires shapely. Install with: pip install shapely") from e


# -----------------------------
# Geometry / metrics (must match your SVG generator)
# -----------------------------
UPM = 1000

# SVG coordinate system (y down). Your design’s "baseline" is y=20.
SVG_BASELINE_Y = 20.0
SVG_TOTAL_H = 30.0  # viewBox height

# Scale SVG units -> font units
SCALE = UPM / SVG_TOTAL_H  # 33.333...

ASCENT = int(round((SVG_BASELINE_Y - 0.0) * SCALE))            # ~667
DESCENT = -int(round((SVG_TOTAL_H - SVG_BASELINE_Y) * SCALE))  # ~-333

# Keep ascent - descent == UPM
if ASCENT - DESCENT != UPM:
    ASCENT = UPM + DESCENT

# Desired default spacing between letters in the FONT (not SVG):
# “same 4 unit used for the vertical bars”
LETTER_SPACING_SVG = 4  # add to advance widths in font space


# -----------------------------
# Glyph selection / naming
# -----------------------------
LETTERS = list("abcdefghijklmnopqrstuvwxyz")
DIGITS = list("0123456789")
LIGATURE_KEYS = ["st", "ch", "ct", "fi", "ij", "sh"]

DIGIT_GLYPH_NAMES = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}


def key_to_glyph_name(key: str) -> str:
    if key in DIGIT_GLYPH_NAMES:
        return DIGIT_GLYPH_NAMES[key]
    return key


# -----------------------------
# SVG parsing
# -----------------------------
Point = Tuple[float, float]


def project_root() -> Path:
    # script lives in a subfolder => project root is exactly one directory above script folder
    return Path(__file__).resolve().parent.parent


def parse_polygon_points(points_str: str) -> List[Point]:
    pts: List[Point] = []
    for token in points_str.replace("\n", " ").replace("\t", " ").split():
        if not token.strip():
            continue
        x_s, y_s = token.split(",")
        pts.append((float(x_s), float(y_s)))
    if len(pts) < 3:
        raise ValueError(f"Polygon has too few points: {points_str!r}")
    return pts


def svg_to_font_xy(x_svg: float, y_svg: float) -> Tuple[int, int]:
    # Flip Y: font y is up; baseline at 0
    x = int(round(x_svg * SCALE))
    y = int(round((SVG_BASELINE_Y - y_svg) * SCALE))
    return x, y


def signed_area_xy(pts: List[Tuple[int, int]]) -> float:
    # Standard signed area in Cartesian coords (y up)
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


# -----------------------------
# Option A: union/merge polygons into continuous outlines
# -----------------------------
def _dedupe_consecutive(pts: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not pts:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _prune_collinear(pts: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Remove strictly collinear points (A-B-C on one straight axis-aligned line).
    Keeps corners; good for your orthogonal grid shapes.
    """
    pts = _dedupe_consecutive(pts)
    n = len(pts)
    if n < 4:
        return pts

    def collinear(a, b, c) -> bool:
        return (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1])

    out: List[Tuple[int, int]] = []
    for i in range(n):
        a = pts[(i - 1) % n]
        b = pts[i]
        c = pts[(i + 1) % n]
        if collinear(a, b, c):
            continue
        out.append(b)

    return out if len(out) >= 3 else pts


def _force_winding(pts: List[Tuple[int, int]], *, clockwise: bool) -> List[Tuple[int, int]]:
    """
    In font coords (y-up), signed_area > 0 => CCW.
    We use:
      - exterior: clockwise  (signed_area < 0)
      - holes:   counterclockwise (signed_area > 0)
    """
    a = signed_area_xy(pts)
    if clockwise and a > 0:
        return list(reversed(pts))
    if (not clockwise) and a < 0:
        return list(reversed(pts))
    return pts


def _ring_svgcoords_to_font_contour(ring_coords) -> List[Tuple[int, int]]:
    """
    ring_coords: sequence of (x,y) from shapely, usually closed (last == first).
    We round to integer SVG coords (your grid is integer-based),
    then map to font coords and prune collinear points.
    """
    coords = [(int(round(x)), int(round(y))) for (x, y) in ring_coords]
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    pts_font = [svg_to_font_xy(float(x), float(y)) for (x, y) in coords]
    pts_font = _prune_collinear(pts_font)
    return pts_font


def load_svg_glyph(svg_path: Path) -> Tuple[int, List[List[Tuple[int, int]]]]:
    """
    Returns:
      (advance_width_svg_units, merged_contours_as_int_points_in_font_coords)

    This unions all SVG polygons first so touching rectangles become one outline
    (and holes are preserved as interior rings).
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.attrib.get("viewBox")
    if not vb:
        raise ValueError(f"No viewBox on {svg_path}")
    _, _, w_s, _h_s = vb.strip().split()
    width_svg = int(round(float(w_s)))

    # collect all polygons
    polys = root.findall(".//{http://www.w3.org/2000/svg}polygon")
    if not polys:
        polys = root.findall(".//polygon")
    if not polys:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    shapes = []
    for p in polys:
        pts_svg = parse_polygon_points(p.attrib["points"])
        pts_svg_i = [(int(round(x)), int(round(y))) for (x, y) in pts_svg]
        pts_svg_i = _dedupe_consecutive(pts_svg_i)
        if len(pts_svg_i) < 3:
            continue

        poly = Polygon(pts_svg_i)
        if not poly.is_valid:
            poly = poly.buffer(0)  # fix self-touching edge cases
        if not poly.is_empty:
            shapes.append(poly)

    if not shapes:
        raise ValueError(f"No valid polygons after parsing: {svg_path}")

    merged = unary_union(shapes)
    if merged.is_empty:
        raise ValueError(f"Union produced empty geometry: {svg_path}")

    if isinstance(merged, Polygon):
        merged_polys = [merged]
    elif isinstance(merged, MultiPolygon):
        merged_polys = list(merged.geoms)
    else:
        merged_polys = [g for g in getattr(merged, "geoms", []) if isinstance(g, Polygon)]

    contours: List[List[Tuple[int, int]]] = []
    for poly in merged_polys:
        # Exterior (filled)
        ext = _ring_svgcoords_to_font_contour(poly.exterior.coords)
        ext = _force_winding(ext, clockwise=True)
        contours.append(ext)

        # Holes
        for hole in poly.interiors:
            h = _ring_svgcoords_to_font_contour(hole.coords)
            h = _force_winding(h, clockwise=False)
            contours.append(h)

    if not contours:
        raise ValueError(f"No contours produced for {svg_path}")

    return width_svg, contours


# -----------------------------
# Glyph construction
# -----------------------------
def build_tt_glyph(contours: List[List[Tuple[int, int]]]) -> object:
    pen = TTGlyphPen(None)
    for contour in contours:
        if not contour or len(contour) < 3:
            continue
        pen.moveTo(contour[0])
        for pt in contour[1:]:
            pen.lineTo(pt)
        pen.closePath()
    return pen.glyph()


def make_notdef_glyph() -> object:
    # Simple .notdef box
    pen = TTGlyphPen(None)
    w = int(round(0.6 * UPM))
    h = int(round(0.8 * UPM))
    x0, y0 = int(round(0.2 * UPM)), int(round(-0.2 * UPM))
    x1, y1 = x0 + w, y0 + h
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()
    return pen.glyph()


def build_fea_liga() -> str:
    # Use glyph names, not unicode literals
    return """
feature liga {
  sub s t by st;
  sub c h by ch;
  sub c t by ct;
  sub f i by fi;
  sub i j by ij;
  sub s h by sh;
} liga;
""".strip() + "\n"


# -----------------------------
# Main build
# -----------------------------
def build_fonts() -> None:
    root = project_root()
    src_dir = root / "src"
    out_dir = root / "dist" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Define build keys
    keys: List[str] = []
    keys.extend(LETTERS)
    keys.extend(DIGITS)
    keys.extend(LIGATURE_KEYS)

    # Glyph order (must include .notdef and space)
    glyph_order: List[str] = [".notdef", "space"]
    for k in keys:
        glyph_order.append(key_to_glyph_name(k))

    # Build glyf + hmtx + cmap
    glyf: Dict[str, object] = {".notdef": make_notdef_glyph()}
    hmtx: Dict[str, Tuple[int, int]] = {}

    # space metrics: one cell + default spacing
    space_adv = int(round((12 + LETTER_SPACING_SVG) * SCALE))
    glyf["space"] = TTGlyphPen(None).glyph()
    hmtx["space"] = (space_adv, 0)
    hmtx[".notdef"] = (space_adv, 0)

    cmap: Dict[int, str] = {}
    for ch in LETTERS:
        cmap[ord(ch)] = ch

    for d in DIGITS:
        cmap[ord(d)] = DIGIT_GLYPH_NAMES[d]

    # Optional: map U+0133 (ĳ) to the ij ligature glyph if present
    cmap[0x0133] = "ij"

    # Load each SVG (merged outlines)
    spacing_adv = int(round(LETTER_SPACING_SVG * SCALE))
    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")

        gname = key_to_glyph_name(k)
        width_svg, contours = load_svg_glyph(svg_path)

        glyf[gname] = build_tt_glyph(contours)

        adv = int(round(width_svg * SCALE)) + spacing_adv
        hmtx[gname] = (adv, 0)

    # Build TTF
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        usWinAscent=ASCENT,
        usWinDescent=-DESCENT,
    )
    fb.setupNameTable(
        {
            "familyName": "unst",
            "styleName": "Regular",
            "uniqueFontIdentifier": "unst Regular",
            "fullName": "unst Regular",
            "psName": "unst-Regular",
            "version": "Version 1.0",
        }
    )
    fb.setupPost()
    fb.setupMaxp()
    fb.setupHead()

    # Add ligature substitutions
    addOpenTypeFeaturesFromString(fb.font, build_fea_liga())

    # Save TTF
    ttf_path = out_dir / "unst.ttf"
    fb.font.save(ttf_path)
    print(f"Wrote: {ttf_path}")

    # Save WOFF
    try:
        woff_font = TTFont(ttf_path)
        woff_font.flavor = "woff"
        woff_path = out_dir / "unst.woff"
        woff_font.save(woff_path)
        print(f"Wrote: {woff_path}")
    except Exception as e:
        print(f"Skipping WOFF (error): {e}")

    # Save WOFF2 (requires brotli)
    try:
        woff2_font = TTFont(ttf_path)
        woff2_font.flavor = "woff2"
        woff2_path = out_dir / "unst.woff2"
        woff2_font.save(woff2_path)
        print(f"Wrote: {woff2_path}")
    except Exception as e:
        print(f"Skipping WOFF2 (install 'brotli' to enable) (error): {e}")


if __name__ == "__main__":
    build_fonts()
