#!/usr/bin/env python3
"""
Build UNST variable font (wdth axis) from the SVG glyphs in ./src.

Input SVGs (expected):
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

Output:
  dist/fonts/unst-variable.ttf
  dist/fonts/unst-variable.woff
  dist/fonts/unst-variable.woff2   (if brotli is available)

Axis:
  wdth: 25 .. 400 (default 100)

Includes GSUB 'liga' substitutions for:
  st, ch, ct, fi, ij, sh

Requires:
  pip install fonttools
Optional for woff2:
  pip install brotli
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import xml.etree.ElementTree as ET

from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    SourceDescriptor,
)
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib import build as var_build

try:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
except Exception as e:
    raise SystemExit("fontTools.feaLib is required (it ships with fonttools).") from e


# -----------------------------
# Geometry / metrics (must match your SVG generator)
# -----------------------------
UPM = 1000

# SVG coordinate system (y down). Baseline is y=20, total height is 30.
SVG_BASELINE_Y = 20.0
SVG_TOTAL_H = 30.0

# Scale SVG units -> font units (Y scale). X scaling is driven by wdth axis.
SCALE_Y = UPM / SVG_TOTAL_H  # 33.333...

# Default spacing BETWEEN glyphs at wdth=100, in SVG units.
# This spacing will SCALE with wdth (so condensed gets tighter, expanded gets looser).
LETTER_SPACING_SVG = 4.0

ASCENT = int(round((SVG_BASELINE_Y - 0.0) * SCALE_Y))            # ~667
DESCENT = -int(round((SVG_TOTAL_H - SVG_BASELINE_Y) * SCALE_Y))  # ~-333
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
    return DIGIT_GLYPH_NAMES.get(key, key)


# -----------------------------
# SVG parsing
# -----------------------------
Point = Tuple[float, float]


def project_root() -> Path:
    # Script lives in a subfolder => project root is exactly one directory above script folder
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


def svg_to_font_xy(x_svg: float, y_svg: float, x_scale: float) -> Tuple[int, int]:
    """
    Convert SVG coords (y down) to font coords (y up) with baseline at y=0.
    Apply x_scale (wdth axis) to X only.
    """
    x = int(round(x_svg * SCALE_Y * x_scale))
    y = int(round((SVG_BASELINE_Y - y_svg) * SCALE_Y))
    return x, y


def signed_area_xy(pts: List[Tuple[int, int]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def load_svg_glyph(svg_path: Path, *, x_scale: float) -> Tuple[int, List[List[Tuple[int, int]]]]:
    """
    Returns:
      (width_svg_units, contours_as_int_points_in_font_coords)
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
    if not polys:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    contours: List[List[Tuple[int, int]]] = []
    for p in polys:
        pts_svg = parse_polygon_points(p.attrib["points"])
        pts_font = [svg_to_font_xy(x, y, x_scale) for (x, y) in pts_svg]

        # Make direction consistent (clockwise in font coords => negative area)
        if signed_area_xy(pts_font) > 0:
            pts_font = list(reversed(pts_font))

        contours.append(pts_font)

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
    return (
        """
feature liga {
  sub s t by st;
  sub c h by ch;
  sub c t by ct;
  sub f i by fi;
  sub i j by ij;
  sub s h by sh;
} liga;
""".strip()
        + "\n"
    )


# -----------------------------
# Master builder
# -----------------------------
def build_master_ttf(
    *,
    out_path: Path,
    style_name: str,
    wdth_value: float,
) -> None:
    """
    Build a static master TTF at a specific wdth value.
    wdth_value is in percent (25..400). x_scale = wdth_value/100.
    """
    x_scale = wdth_value / 100.0

    root = project_root()
    src_dir = root / "src"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    keys: List[str] = []
    keys.extend(LETTERS)
    keys.extend(DIGITS)
    keys.extend(LIGATURE_KEYS)

    glyph_order: List[str] = [".notdef", "space"] + [key_to_glyph_name(k) for k in keys]

    glyf: Dict[str, object] = {".notdef": make_notdef_glyph()}
    hmtx: Dict[str, Tuple[int, int]] = {}

    # Space: (12 + spacing) scaled with wdth
    space_adv = int(round((12.0 + LETTER_SPACING_SVG) * SCALE_Y * x_scale))
    glyf["space"] = TTGlyphPen(None).glyph()
    hmtx["space"] = (space_adv, 0)
    hmtx[".notdef"] = (space_adv, 0)

    cmap: Dict[int, str] = {}
    for ch in LETTERS:
        cmap[ord(ch)] = ch
    for d in DIGITS:
        cmap[ord(d)] = DIGIT_GLYPH_NAMES[d]
    cmap[0x0020] = "space"  # space
    cmap[0x0133] = "ij"     # ĳ

    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")

        gname = key_to_glyph_name(k)
        width_svg, contours = load_svg_glyph(svg_path, x_scale=x_scale)

        glyf[gname] = build_tt_glyph(contours)

        # Advance width = (tight viewBox width + base spacing) scaled with wdth
        # If you ever want spacing NOT to scale with wdth, use:
        #   adv = int(round(width_svg * SCALE_Y * x_scale + LETTER_SPACING_SVG * SCALE_Y))
        adv = int(round((float(width_svg) + LETTER_SPACING_SVG) * SCALE_Y * x_scale))
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
            "styleName": style_name,
            "uniqueFontIdentifier": f"unst {style_name}",
            "fullName": f"unst {style_name}",
            "psName": f"unst-{style_name}".replace(" ", ""),
            "version": "Version 1.0",
        }
    )
    fb.setupPost()
    fb.setupMaxp()
    fb.setupHead()

    addOpenTypeFeaturesFromString(fb.font, build_fea_liga())

    fb.font.save(out_path)


# -----------------------------
# Variable font builder
# -----------------------------
def build_variable_font() -> None:
    root = project_root()
    out_dir = root / "dist" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    masters_dir = out_dir / "_vf_masters"
    masters_dir.mkdir(parents=True, exist_ok=True)

    # Three masters so default is exact and not interpolated.
    masters = [
        {"wdth": 25.0, "style": "Condensed"},
        {"wdth": 100.0, "style": "Regular"},
        {"wdth": 400.0, "style": "Expanded"},
    ]

    # Build masters
    master_paths: Dict[float, Path] = {}
    for m in masters:
        p = masters_dir / f"unst-wdth{int(m['wdth'])}.ttf"
        build_master_ttf(out_path=p, style_name=m["style"], wdth_value=m["wdth"])
        master_paths[m["wdth"]] = p
        print(f"Wrote master: {p}")

    # Build designspace (IMPORTANT: location keys must match axis.name, not axis.tag)
    ds = DesignSpaceDocument()

    axis = AxisDescriptor()
    axis.tag = "wdth"
    axis.name = "Width"      # <-- axis NAME
    axis.minimum = 25.0
    axis.default = 100.0
    axis.maximum = 400.0
    ds.addAxis(axis)

    for m in masters:
        s = SourceDescriptor()
        s.name = f"unst-{m['style']}"
        # store relative path from designspace file (in out_dir) to the master file
        rel = master_paths[m["wdth"]].relative_to(out_dir).as_posix()
        s.filename = rel
        s.location = {"Width": m["wdth"]}  # <-- MUST match axis.name ("Width")
        if m["wdth"] == 100.0:
            # Make the default master the base for metadata/features/lib where applicable
            s.copyInfo = True
            s.copyLib = True
            s.copyFeatures = True
        ds.addSource(s)

    designspace_path = out_dir / "unst.designspace"
    ds.write(designspace_path)

    # Build VF
    res = var_build(str(designspace_path), optimize=True)
    vf = res[0] if isinstance(res, tuple) else res

    var_ttf_path = out_dir / "unst-variable.ttf"
    vf.save(var_ttf_path)
    print(f"Wrote: {var_ttf_path}")

    # WOFF
    try:
        woff_font = TTFont(var_ttf_path)
        woff_font.flavor = "woff"
        woff_path = out_dir / "unst-variable.woff"
        woff_font.save(woff_path)
        print(f"Wrote: {woff_path}")
    except Exception as e:
        print(f"Skipping WOFF (error): {e}")

    # WOFF2
    try:
        woff2_font = TTFont(var_ttf_path)
        woff2_font.flavor = "woff2"
        woff2_path = out_dir / "unst-variable.woff2"
        woff2_font.save(woff2_path)
        print(f"Wrote: {woff2_path}")
    except Exception as e:
        print(f"Skipping WOFF2 (install 'brotli' to enable) (error): {e}")


if __name__ == "__main__":
    build_variable_font()
