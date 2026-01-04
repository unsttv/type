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

Requires:
  pip install fonttools
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


# -----------------------------
# Geometry / metrics (must match your SVG generator)
# -----------------------------
UPM = 1000

# SVG coordinate system (y down). Your design’s "baseline" is y=20.
SVG_BASELINE_Y = 20.0
SVG_TOTAL_H = 30.0  # viewBox height

# Scale SVG units -> font units
SCALE = UPM / SVG_TOTAL_H  # 33.333...

# Default spacing BETWEEN glyphs, in SVG units (matches your vertical bar thickness / gap logic)
LETTER_SPACING_SVG = 4.0

ASCENT = int(round((SVG_BASELINE_Y - 0.0) * SCALE))            # y=0 is top => ~667
DESCENT = -int(round((SVG_TOTAL_H - SVG_BASELINE_Y) * SCALE))  # y=30 => ~-333
# Make sure ascent - descent == UPM
if ASCENT - DESCENT != UPM:
    ASCENT = UPM + DESCENT


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


def load_svg_glyph(svg_path: Path) -> Tuple[int, List[List[Tuple[int, int]]]]:
    """
    Returns:
      (advance_width_svg_units, contours_as_int_points_in_font_coords)
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.attrib.get("viewBox")
    if not vb:
        raise ValueError(f"No viewBox on {svg_path}")
    _, _, w_s, _h_s = vb.strip().split()
    width_svg = int(round(float(w_s)))

    polys = root.findall(".//{http://www.w3.org/2000/svg}polygon")
    if not polys:
        polys = root.findall(".//polygon")

    contours: List[List[Tuple[int, int]]] = []
    for p in polys:
        pts_svg = parse_polygon_points(p.attrib["points"])
        pts_font = [svg_to_font_xy(x, y) for (x, y) in pts_svg]

        # Ensure contour direction is consistent (clockwise in font coords => negative signed area)
        if signed_area_xy(pts_font) > 0:
            pts_font = list(reversed(pts_font))

        contours.append(pts_font)

    if not contours:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    return width_svg, contours


# -----------------------------
# Glyph construction
# -----------------------------
def build_tt_glyph(contours: List[List[Tuple[int, int]]]) -> object:
    pen = TTGlyphPen(None)
    for contour in contours:
        pen.moveTo(contour[0])
        for pt in contour[1:]:
            pen.lineTo(pt)
        pen.closePath()
    return pen.glyph()


def make_notdef_glyph() -> object:
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

    keys: List[str] = []
    keys.extend(LETTERS)
    keys.extend(DIGITS)
    keys.extend(LIGATURE_KEYS)

    glyph_order: List[str] = [".notdef", "space"]
    for k in keys:
        glyph_order.append(key_to_glyph_name(k))

    glyf: Dict[str, object] = {".notdef": make_notdef_glyph()}
    hmtx: Dict[str, Tuple[int, int]] = {}

    # Space: one cell (12) + default spacing (4) so it's not tighter than normal letter spacing
    space_adv = int(round((12.0 + LETTER_SPACING_SVG) * SCALE))
    glyf["space"] = TTGlyphPen(None).glyph()
    hmtx["space"] = (space_adv, 0)
    hmtx[".notdef"] = (space_adv, 0)

    cmap: Dict[int, str] = {}
    for ch in LETTERS:
        cmap[ord(ch)] = ch
    for d in DIGITS:
        cmap[ord(d)] = DIGIT_GLYPH_NAMES[d]
    cmap[0x0133] = "ij"  # ĳ

    # Load each SVG
    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")

        gname = key_to_glyph_name(k)
        width_svg, contours = load_svg_glyph(svg_path)

        glyf[gname] = build_tt_glyph(contours)

        # Add default spacing to advance width (right-side bearing effect)
        adv_svg = float(width_svg) + LETTER_SPACING_SVG
        adv = int(round(adv_svg * SCALE))
        hmtx[gname] = (adv, 0)

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

    addOpenTypeFeaturesFromString(fb.font, build_fea_liga())

    ttf_path = out_dir / "unst.ttf"
    fb.font.save(ttf_path)
    print(f"Wrote: {ttf_path}")

    try:
        woff_font = TTFont(ttf_path)
        woff_font.flavor = "woff"
        woff_path = out_dir / "unst.woff"
        woff_font.save(woff_path)
        print(f"Wrote: {woff_path}")
    except Exception as e:
        print(f"Skipping WOFF (error): {e}")

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
