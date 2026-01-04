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

Thin-line behavior:
  - Thin vertical connector bars (1 SVG unit wide, tall) do NOT scale in thickness.
  - When wdth < 100%, we also shift the "right side" of the ligature by (1 - x_scale)
    SVG units, so spacing between the thin connector and the next vertical matches the
    same scaled spacing as other thick bars.

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

# Y-scale (SVG units -> font units). X is also based on this, plus wdth scaling.
SCALE_Y = UPM / SVG_TOTAL_H  # 33.333...

# Default spacing between glyphs at wdth=100, in SVG units.
# This spacing scales with wdth (as in your earlier build).
LETTER_SPACING_SVG = 4.0

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
# SVG parsing helpers
# -----------------------------
Point = Tuple[float, float]
IntPoint = Tuple[int, int]
EPS = 1e-6


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


def signed_area_xy(pts: List[IntPoint]) -> float:
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
    Detect the vertical thin connector used in st-like ligatures:
      width == 1 unit, tall (~10 units), top-anchored (y near 0)
    """
    w = maxx - minx
    h = maxy - miny
    if abs(w - 1.0) > EPS:
        return False
    if h < 9.0 - EPS:
        return False
    if miny > 0.01:
        return False
    return True


def find_internal_thin_strip_for_st(pts_svg: List[Point]) -> Optional[Tuple[float, float]]:
    """
    'st' is one combined polygon (not separate thin-rect polygon).
    Find an internal x pair (x, x+1) that appears in the upper zone (y<=10.1),
    is top-anchored, and spans tall enough.
    Returns (x_left, x_right) or None.
    """
    y_cut = 10.1
    upper = [(x, y) for (x, y) in pts_svg if y <= y_cut]
    if len(upper) < 4:
        return None

    xs = sorted({x for (x, _y) in upper})
    xset = set(xs)

    candidates: List[Tuple[float, float, float]] = []  # (xL, xR, span)

    for xL in xs:
        xR = xL + 1.0
        if not any(abs(v - xR) < EPS for v in xset):
            continue

        ysL = [y for (xx, y) in upper if abs(xx - xL) < EPS]
        ysR = [y for (xx, y) in upper if abs(xx - xR) < EPS]
        if not ysL or not ysR:
            continue

        y_min = min(min(ysL), min(ysR))
        y_max = max(max(ysL), max(ysR))
        span = y_max - y_min

        if y_min <= 0.01 and span >= 9.0 - EPS:
            candidates.append((xL, xR, span))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[2], reverse=True)
    return (candidates[0][0], candidates[0][1])


def transform_x(
    x_svg: float,
    *,
    x_scale: float,
    right_threshold: Optional[float],
    right_shift: float,
    frozen_strip: Optional[Tuple[float, float]],
) -> float:
    """
    Piecewise X transform:

    - Default: x * x_scale
    - If x >= right_threshold and right_shift>0: add right_shift (fix crowding at wdth<100)
    - If frozen_strip=(xL,xR) and x is exactly on xL or xR: force bar width to stay 1:
        xL -> xL*x_scale
        xR -> xL*x_scale + (xR-xL)   (== +1)
      (no right_shift applied to the strip edges; they stay anchored to the left edge)
    """
    x_eff = x_svg * x_scale

    if right_threshold is not None and right_shift > 0.0 and x_svg >= right_threshold - EPS:
        x_eff += right_shift

    if frozen_strip is not None:
        xL, xR = frozen_strip
        w = xR - xL
        if abs(x_svg - xL) < EPS:
            x_eff = xL * x_scale
        elif abs(x_svg - xR) < EPS:
            x_eff = (xL * x_scale) + w  # keep bar width constant (w should be 1)

    return x_eff


def svg_to_font_xy(
    x_svg: float,
    y_svg: float,
    *,
    x_scale: float,
    right_threshold: Optional[float],
    right_shift: float,
    frozen_strip: Optional[Tuple[float, float]],
) -> IntPoint:
    # Y: flip + scale to UPM space
    y = int(round((SVG_BASELINE_Y - y_svg) * SCALE_Y))
    # X: piecewise transform, then scale to font units
    x_eff = transform_x(
        x_svg,
        x_scale=x_scale,
        right_threshold=right_threshold,
        right_shift=right_shift,
        frozen_strip=frozen_strip,
    )
    x = int(round(x_eff * SCALE_Y))
    return x, y


def load_svg_glyph(
    svg_path: Path,
    *,
    x_scale: float,
    glyph_key: str,
) -> Tuple[int, List[List[IntPoint]], float]:
    """
    Returns:
      (width_svg_units, contours_in_font_coords, extra_advance_svg_units)
    extra_advance_svg_units is used to keep spacing sane when we add right_shift at wdth<100.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.attrib.get("viewBox")
    if not vb:
        raise ValueError(f"No viewBox on {svg_path}")
    _, _, w_s, _h_s = vb.strip().split()
    width_svg = int(round(float(w_s)))

    polys_el = root.findall(".//{http://www.w3.org/2000/svg}polygon")
    if not polys_el:
        polys_el = root.findall(".//polygon")
    if not polys_el:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    # Parse all polygons first (we need global info per glyph)
    polys_svg: List[List[Point]] = [parse_polygon_points(p.attrib["points"]) for p in polys_el]

    # Identify a frozen 1-unit strip (either a dedicated thin-rect polygon, or internal strip for 'st')
    frozen_strip: Optional[Tuple[float, float]] = None
    thin_poly_index: Optional[int] = None

    for idx, pts in enumerate(polys_svg):
        minx, maxx, miny, maxy = bbox_svg(pts)
        if is_thin_vertical_connector(minx, maxx, miny, maxy):
            frozen_strip = (minx, maxx)  # width ~1
            thin_poly_index = idx
            break

    if frozen_strip is None and glyph_key == "st":
        # Try internal detection for the monogram polygon
        frozen_strip = find_internal_thin_strip_for_st(polys_svg[0])

    # If we freeze a strip and we are CONDENSING (<100%), compensate spacing by shifting "right side"
    right_shift = 0.0
    right_threshold: Optional[float] = None
    extra_advance_svg = 0.0

    if frozen_strip is not None and x_scale < 1.0 - EPS:
        # This is exactly the amount of "extra thickness" compared to normal scaling:
        # normal would have scaled the bar width to (1*x_scale); we keep it 1, so + (1-x_scale).
        right_shift = 1.0 - x_scale
        extra_advance_svg = right_shift  # add to advance so the glyph doesn't collide with next one

        xL, xR = frozen_strip

        # Prefer to shift only the right glyph portion (not the left part, not the strip itself).
        # Determine where the right-hand content begins by scanning polygon bboxes.
        starts: List[float] = []
        for i, pts in enumerate(polys_svg):
            if thin_poly_index is not None and i == thin_poly_index:
                continue  # the vertical thin bar itself
            minx, maxx, _miny, _maxy = bbox_svg(pts)
            # anything whose minx is strictly to the right of the strip's right edge is "right side"
            if minx > xR + EPS:
                starts.append(minx)

        if starts:
            right_threshold = min(starts)
        else:
            # Fallback (shouldn't happen): shift anything to the right of the strip
            right_threshold = xR + EPS

    # Convert each polygon to font contours
    contours: List[List[IntPoint]] = []
    for pts_svg in polys_svg:
        pts_font = [
            svg_to_font_xy(
                x, y,
                x_scale=x_scale,
                right_threshold=right_threshold,
                right_shift=right_shift,
                frozen_strip=frozen_strip,
            )
            for (x, y) in pts_svg
        ]

        # Make contour direction consistent (clockwise in font coords => negative area)
        if signed_area_xy(pts_font) > 0:
            pts_font = list(reversed(pts_font))

        contours.append(pts_font)

    return width_svg, contours, extra_advance_svg


# -----------------------------
# Glyph construction
# -----------------------------
def build_tt_glyph(contours: List[List[IntPoint]]) -> object:
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

    # Space: one cell + spacing, scaled by wdth
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
    cmap[0x0133] = "ij"  # ĳ

    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")

        gname = key_to_glyph_name(k)
        width_svg, contours, extra_adv_svg = load_svg_glyph(svg_path, x_scale=x_scale, glyph_key=k)

        glyf[gname] = build_tt_glyph(contours)

        # Base advance: (tight viewBox width + spacing) scaled by wdth
        adv_svg_scaled = (float(width_svg) + LETTER_SPACING_SVG) * x_scale

        # If we had to right-shift content to compensate for frozen thin bar at wdth<100,
        # give the glyph extra advance (in SVG units) so it doesn't collide with next glyph.
        adv_svg_scaled += extra_adv_svg

        adv = int(round(adv_svg_scaled * SCALE_Y))
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

    # Designspace: IMPORTANT: source.location keys must match axis.name (not axis.tag)
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
