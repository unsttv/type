#!/usr/bin/env python3
"""
Build UNST variable font (wdth axis) from the SVG glyphs in ./src.

Output:
  dist/fonts/unst-variable.ttf
  dist/fonts/unst-variable.woff
  dist/fonts/unst-variable.woff2   (if brotli is available)

Axis:
  wdth: 25 .. 400 (default 100)

Includes GSUB 'liga' substitutions for:
  st, ch, ct, fi, ij, sh

Special behavior:
  - Thin vertical connector rectangles (1 SVG unit wide, tall) do NOT scale in thickness.
    Their position scales, but their width stays 1 unit, anchored to the rectangle's LEFT edge.
  - For "st" (single combined polygon), we also freeze the internal 1-unit strip in the
    upper zone (y<=10) so it behaves like the other ligatures.

Requires:
  pip install fonttools
Optional for woff2:
  pip install brotli
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional

import xml.etree.ElementTree as ET

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
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

SVG_BASELINE_Y = 20.0
SVG_TOTAL_H = 30.0

SCALE_Y = UPM / SVG_TOTAL_H  # 33.333...

LETTER_SPACING_SVG = 4.0  # scales with wdth

ASCENT = int(round((SVG_BASELINE_Y - 0.0) * SCALE_Y))
DESCENT = -int(round((SVG_TOTAL_H - SVG_BASELINE_Y) * SCALE_Y))
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


def signed_area_xy(pts: List[Tuple[int, int]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def bbox_svg(pts: List[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


def is_thin_vertical_connector(minx: float, maxx: float, miny: float, maxy: float) -> bool:
    """
    Detect the special 1-unit-wide vertical connector used in 'st-like' ligatures.
    """
    eps = 1e-6
    w = maxx - minx
    h = maxy - miny

    if abs(w - 1.0) > eps:
        return False
    if h < 9.0 - eps:
        return False
    if miny > 0.01:
        return False
    return True


def find_internal_thin_strip_for_st(pts_svg: List[Point]) -> Optional[Tuple[float, float]]:
    """
    "st" is one big polygon. The thin connector is an INTERNAL 1-unit strip in the upper zone.
    We detect an x pair (x, x+1) that both appear among points with y<=10.1 and span tall enough.
    Returns (x_left, x_right) in SVG units, or None if not found.
    """
    eps = 1e-6
    y_cut = 10.1

    upper = [(x, y) for (x, y) in pts_svg if y <= y_cut]
    if len(upper) < 4:
        return None

    xs = sorted({x for (x, _y) in upper})
    xset = set(xs)

    candidates: List[Tuple[float, float, float]] = []  # (x, x+1, height_span)

    for x in xs:
        xp = x + 1.0
        # Exact integer-ish grid, but be tolerant: require presence of a value ~x+1
        has_xp = any(abs(v - xp) < eps for v in xset)
        if not has_xp:
            continue

        ys_x = [y for (xx, y) in upper if abs(xx - x) < eps]
        ys_xp = [y for (xx, y) in upper if abs(xx - xp) < eps]

        if not ys_x or not ys_xp:
            continue

        y_min = min(min(ys_x), min(ys_xp))
        y_max = max(max(ys_x), max(ys_xp))
        span = y_max - y_min

        # Prefer top-anchored + tall
        if y_min <= 0.01 and span >= 9.0 - eps:
            candidates.append((x, xp, span))

    if not candidates:
        return None

    # Pick the tallest span candidate (usually unique)
    candidates.sort(key=lambda t: t[2], reverse=True)
    return (candidates[0][0], candidates[0][1])


def svg_to_font_xy(
    x_svg: float,
    y_svg: float,
    *,
    x_scale: float,
    thin_minx: float | None = None,
    thin_maxx: float | None = None,
    internal_strip: Tuple[float, float] | None = None,
) -> Tuple[int, int]:
    """
    Convert SVG coords (y down) to font coords (y up) with baseline at y=0.

    X is scaled by x_scale EXCEPT:
      1) If thin_minx/maxx are given (the whole polygon is the thin bar),
         freeze its width anchored to left edge.
      2) If internal_strip is given (for "st"), and point is on one of its x-edges in the
         upper zone, freeze that strip width anchored to left edge.
    """
    eps = 1e-6
    y = int(round((SVG_BASELINE_Y - y_svg) * SCALE_Y))

    # Case A: the whole polygon is a thin connector rectangle
    if thin_minx is not None and thin_maxx is not None:
        w = thin_maxx - thin_minx
        left = thin_minx * x_scale
        right = left + w

        if abs(x_svg - thin_minx) < eps:
            x_eff = left
        elif abs(x_svg - thin_maxx) < eps:
            x_eff = right
        else:
            t = (x_svg - thin_minx) / w
            x_eff = left + t * w

        x = int(round(x_eff * SCALE_Y))
        return x, y

    # Case B: internal strip in "st" (only apply in upper zone, y<=10.1)
    if internal_strip is not None and y_svg <= 10.1 + eps:
        xL, xR = internal_strip
        w = xR - xL
        if abs(w - 1.0) < 1e-3:  # sanity
            left = xL * x_scale
            right = left + w
            if abs(x_svg - xL) < eps:
                x_eff = left
                x = int(round(x_eff * SCALE_Y))
                return x, y
            if abs(x_svg - xR) < eps:
                x_eff = right
                x = int(round(x_eff * SCALE_Y))
                return x, y

    # Normal scaling
    x = int(round((x_svg * x_scale) * SCALE_Y))
    return x, y


def load_svg_glyph(
    svg_path: Path,
    *,
    x_scale: float,
    glyph_key: str | None = None,
) -> Tuple[int, List[List[Tuple[int, int]]]]:
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
        minx, maxx, miny, maxy = bbox_svg(pts_svg)

        thin = is_thin_vertical_connector(minx, maxx, miny, maxy)
        thin_minx = minx if thin else None
        thin_maxx = maxx if thin else None

        internal_strip = None
        # Only needed for the combined monogram in "st"
        if glyph_key == "st" and not thin:
            internal_strip = find_internal_thin_strip_for_st(pts_svg)

        pts_font = [
            svg_to_font_xy(
                x, y,
                x_scale=x_scale,
                thin_minx=thin_minx,
                thin_maxx=thin_maxx,
                internal_strip=internal_strip
            )
            for (x, y) in pts_svg
        ]

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
def build_master_ttf(*, out_path: Path, style_name: str, wdth_value: float) -> None:
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

    space_adv = int(round((12.0 + LETTER_SPACING_SVG) * SCALE_Y * x_scale))
    glyf["space"] = TTGlyphPen(None).glyph()
    hmtx["space"] = (space_adv, 0)
    hmtx[".notdef"] = (space_adv, 0)

    cmap: Dict[int, str] = {}
    for ch in LETTERS:
        cmap[ord(ch)] = ch
    for d in DIGITS:
        cmap[ord(d)] = DIGIT_GLYPH_NAMES[d]
    cmap[0x0020] = "space"
    cmap[0x0133] = "ij"

    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")

        gname = key_to_glyph_name(k)
        width_svg, contours = load_svg_glyph(svg_path, x_scale=x_scale, glyph_key=k)

        glyf[gname] = build_tt_glyph(contours)
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

    masters = [
        {"wdth": 25.0, "style": "Condensed"},
        {"wdth": 100.0, "style": "Regular"},
        {"wdth": 400.0, "style": "Expanded"},
    ]

    master_paths: Dict[float, Path] = {}
    for m in masters:
        p = masters_dir / f"unst-wdth{int(m['wdth'])}.ttf"
        build_master_ttf(out_path=p, style_name=m["style"], wdth_value=m["wdth"])
        master_paths[m["wdth"]] = p
        print(f"Wrote master: {p}")

    ds = DesignSpaceDocument()

    axis = AxisDescriptor()
    axis.tag = "wdth"
    axis.name = "Width"
    axis.minimum = 25.0
    axis.default = 100.0
    axis.maximum = 400.0
    ds.addAxis(axis)

    for m in masters:
        s = SourceDescriptor()
        s.name = f"unst-{m['style']}"
        rel = master_paths[m["wdth"]].relative_to(out_dir).as_posix()
        s.filename = rel
        s.location = {"Width": m["wdth"]}
        if m["wdth"] == 100.0:
            s.copyInfo = True
            s.copyLib = True
            s.copyFeatures = True
        ds.addSource(s)

    designspace_path = out_dir / "unst.designspace"
    ds.write(designspace_path)

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
