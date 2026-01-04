#!/usr/bin/env python3
"""
Build UNST variable font from SVG glyphs in ./src with two axes:

  wdth: 25 .. 400 (default 100)
  hght: 25 .. 400 (default 100)   (custom axis tag)

Outputs:
  dist/fonts/unst-variable.ttf
  dist/fonts/unst-variable.woff
  dist/fonts/unst-variable.woff2   (if brotli is available)

Includes GSUB 'liga' substitutions for:
  st, ch, ct, fi, ij, sh

Special behavior for ligature connector strokes:
  - thin vertical connector bars (1 SVG unit wide, tall) do NOT scale in width
  - thin horizontal connector bars (1 SVG unit tall, at top) do NOT scale in height
  - when wdth < 100%, we shift the "right side" of the ligature by (1 - x_scale)
    SVG units to preserve the same spacing as thick bars
  - for "st" (single polygon), we also:
      * freeze the internal 1-unit vertical strip in the upper zone
      * freeze the top 1-unit horizontal strip (y=0..1)
      * apply the condensed right-side shift only from the true start of the "t" part
        (prevents the bottom-right of the "s" from being affected)

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

# Base SVG->font scaling (for wdth=100/hght=100)
SCALE_BASE = UPM / SVG_TOTAL_H  # 33.333...

LETTER_SPACING_SVG = 4.0  # scales with wdth

# Axis limits
WDTH_MIN, WDTH_DEF, WDTH_MAX = 25.0, 100.0, 400.0
HGHT_MIN, HGHT_DEF, HGHT_MAX = 25.0, 100.0, 400.0
MAX_Y_SCALE = HGHT_MAX / 100.0  # 4.0

# Set font metrics big enough for max height (hght=400%)
# We scale y about baseline. At hght=400:
#   top y (0) -> baseline + (0-baseline)*4 = -60
#   bottom y (30) -> baseline + (30-baseline)*4 = 60
TOP_Y_AT_MAX = SVG_BASELINE_Y + (0.0 - SVG_BASELINE_Y) * MAX_Y_SCALE      # -60
BOT_Y_AT_MAX = SVG_BASELINE_Y + (SVG_TOTAL_H - SVG_BASELINE_Y) * MAX_Y_SCALE  # 60

ASCENT = int(round((SVG_BASELINE_Y - TOP_Y_AT_MAX) * SCALE_BASE))   # 80 * 33.33 = 2667
DESCENT = -int(round((BOT_Y_AT_MAX - SVG_BASELINE_Y) * SCALE_BASE)) # -40 * 33.33 = -1333

EPS = 1e-6

Point = Tuple[float, float]
IntPoint = Tuple[int, int]


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


def project_root() -> Path:
    # script lives in a subfolder => project root is exactly one directory above script folder
    return Path(__file__).resolve().parent.parent


# -----------------------------
# Helpers: parsing + geometry
# -----------------------------
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


def scale_y_about_baseline(y_svg: float, y_scale: float) -> float:
    # baseline stays fixed
    return SVG_BASELINE_Y + (y_svg - SVG_BASELINE_Y) * y_scale


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


def is_thin_horizontal_connector_for_ligature(minx: float, maxx: float, miny: float, maxy: float, glyph_key: str) -> bool:
    """
    Detect the top horizontal connector bar in st-like ligatures (ch/ct/sh).
    We restrict this to those glyph keys to avoid catching normal letter strokes.
    """
    if glyph_key not in {"ch", "ct", "sh"}:
        return False
    h = maxy - miny
    if abs(h - 1.0) > EPS:
        return False
    if miny > 0.01:  # should be at y=0..1
        return False
    # must be "long-ish"
    if (maxx - minx) < 2.0 - EPS:
        return False
    return True


def find_internal_thin_vstrip_for_st(pts_svg: List[Point]) -> Optional[Tuple[float, float]]:
    """
    'st' is one combined polygon (not separate thin-rect polygon).
    Find an internal x pair (x, x+1) in the upper zone (y<=10.1) that's top-anchored and tall.
    Returns (x_left, x_right) or None.
    """
    y_cut = 10.1
    upper = [(x, y) for (x, y) in pts_svg if y <= y_cut]
    if len(upper) < 4:
        return None

    xs = sorted({x for (x, _y) in upper})
    xset = set(xs)

    best: Optional[Tuple[float, float, float]] = None  # (xL, xR, span)

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
            cand = (xL, xR, span)
            if best is None or cand[2] > best[2]:
                best = cand

    if best is None:
        return None
    return (best[0], best[1])


# -----------------------------
# Piecewise transforms (wdth + hght + thin connector freezing)
# -----------------------------
def transform_x(
    x_svg: float,
    *,
    x_scale: float,
    right_threshold: Optional[float],
    right_shift: float,
    frozen_vstrip: Optional[Tuple[float, float]],
    vstrip_upper_only: bool,
    y_svg: float,
) -> float:
    """
    X transform:
      - default: x * x_scale
      - if x >= right_threshold and right_shift>0: add right_shift (condensed spacing compensation)
      - if frozen_vstrip=(xL,xR): keep strip width constant (=xR-xL), anchored to xL*x_scale
        If vstrip_upper_only=True, only freeze when y<=10.1 (to match your intent for st).
    """
    x_eff = x_svg * x_scale

    if right_threshold is not None and right_shift > 0.0 and x_svg >= right_threshold - EPS:
        x_eff += right_shift

    if frozen_vstrip is not None:
        xL, xR = frozen_vstrip
        w = xR - xL  # should be 1
        if (not vstrip_upper_only) or (y_svg <= 10.1 + EPS):
            if abs(x_svg - xL) < EPS:
                x_eff = xL * x_scale
            elif abs(x_svg - xR) < EPS:
                x_eff = (xL * x_scale) + w

    return x_eff


def transform_y(
    y_svg: float,
    *,
    y_scale: float,
    frozen_hstrip: Optional[Tuple[float, float]],
) -> float:
    """
    Y transform (SVG y-down):
      - default: scale about baseline
      - if frozen_hstrip=(y0,y1): keep thickness constant (=y1-y0), anchored to scaled y0
    """
    if frozen_hstrip is None:
        return scale_y_about_baseline(y_svg, y_scale)

    y0, y1 = frozen_hstrip
    h = y1 - y0  # should be 1

    # First scale the anchor edge y0 about baseline
    y0_eff = scale_y_about_baseline(y0, y_scale)

    if abs(y_svg - y0) < EPS:
        return y0_eff
    if abs(y_svg - y1) < EPS:
        return y0_eff + h

    # Fallback: scale relative within the strip (shouldn't happen for axis-aligned rectangle points)
    t = (y_svg - y0) / h
    return y0_eff + t * h


def svg_to_font_xy(
    x_svg: float,
    y_svg: float,
    *,
    x_scale: float,
    y_scale: float,
    right_threshold: Optional[float],
    right_shift: float,
    frozen_vstrip: Optional[Tuple[float, float]],
    vstrip_upper_only: bool,
    frozen_hstrip: Optional[Tuple[float, float]],
) -> IntPoint:
    # Apply transforms in SVG space
    y_eff = transform_y(y_svg, y_scale=y_scale, frozen_hstrip=frozen_hstrip)
    x_eff = transform_x(
        x_svg,
        x_scale=x_scale,
        right_threshold=right_threshold,
        right_shift=right_shift,
        frozen_vstrip=frozen_vstrip,
        vstrip_upper_only=vstrip_upper_only,
        y_svg=y_svg,
    )

    # Convert to font coords (y up, baseline at 0)
    x = int(round(x_eff * SCALE_BASE))
    y = int(round((SVG_BASELINE_Y - y_eff) * SCALE_BASE))
    return x, y


# -----------------------------
# SVG -> contours loader (with thin-stroke logic + condensed compensation)
# -----------------------------
def load_svg_glyph(
    svg_path: Path,
    *,
    x_scale: float,
    y_scale: float,
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

    polys_svg: List[List[Point]] = [parse_polygon_points(p.attrib["points"]) for p in polys_el]

    frozen_vstrip: Optional[Tuple[float, float]] = None
    vstrip_upper_only = False
    frozen_hstrip: Optional[Tuple[float, float]] = None
    thin_v_poly_index: Optional[int] = None

    # First pass: detect dedicated connector polygons (ch/ct/sh)
    for idx, pts in enumerate(polys_svg):
        minx, maxx, miny, maxy = bbox_svg(pts)

        if frozen_vstrip is None and is_thin_vertical_connector(minx, maxx, miny, maxy):
            frozen_vstrip = (minx, maxx)
            thin_v_poly_index = idx

        if frozen_hstrip is None and is_thin_horizontal_connector_for_ligature(minx, maxx, miny, maxy, glyph_key):
            frozen_hstrip = (miny, maxy)  # should be (0,1)

    # Special handling for st (single polygon): internal v-strip + top h-strip
    if glyph_key == "st":
        if frozen_vstrip is None:
            v = find_internal_thin_vstrip_for_st(polys_svg[0])
            if v is not None:
                frozen_vstrip = v
                vstrip_upper_only = True  # only freeze the upper portion
        # Freeze the top strip height (y=0..1) for the connector in st
        # (keeps the "thin" horizontal connector line consistent)
        frozen_hstrip = (0.0, 1.0)

    # Condensed compensation for frozen vertical strip: shift right side by (1 - x_scale)
    right_shift = 0.0
    right_threshold: Optional[float] = None
    extra_advance_svg = 0.0

    if frozen_vstrip is not None and x_scale < 1.0 - EPS:
        right_shift = 1.0 - x_scale
        extra_advance_svg = right_shift

        xL, xR = frozen_vstrip

        if glyph_key == "st":
            # IMPORTANT: st is a single polygon: don't shift the 's' portion.
            # Find the next "real" x column after the strip that indicates the start of the 't' part.
            xs = sorted({x for (x, _y) in polys_svg[0]})
            # Skip the strip and the immediate area of the 's' right edge (xR itself).
            candidates = [x for x in xs if x > (xR + 1.0 + EPS)]
            right_threshold = min(candidates) if candidates else (xR + 1.0 + EPS)
        else:
            # For multi-polygon ligatures: shift polygons that begin to the right of the strip.
            starts: List[float] = []
            for i, pts in enumerate(polys_svg):
                if thin_v_poly_index is not None and i == thin_v_poly_index:
                    continue
                minx, _maxx, _miny, _maxy = bbox_svg(pts)
                if minx > xR + EPS:
                    starts.append(minx)
            right_threshold = min(starts) if starts else (xR + 1.0 + EPS)

    # Build contours
    contours: List[List[IntPoint]] = []
    for pts_svg in polys_svg:
        pts_font = [
            svg_to_font_xy(
                x, y,
                x_scale=x_scale,
                y_scale=y_scale,
                right_threshold=right_threshold,
                right_shift=right_shift,
                frozen_vstrip=frozen_vstrip,
                vstrip_upper_only=vstrip_upper_only,
                frozen_hstrip=frozen_hstrip,
            )
            for (x, y) in pts_svg
        ]

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
def build_master_ttf(*, out_path: Path, style_name: str, wdth_value: float, hght_value: float) -> None:
    x_scale = wdth_value / 100.0
    y_scale = hght_value / 100.0

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
    space_adv = int(round((12.0 + LETTER_SPACING_SVG) * SCALE_BASE * x_scale))
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
        width_svg, contours, extra_adv_svg = load_svg_glyph(
            svg_path,
            x_scale=x_scale,
            y_scale=y_scale,
            glyph_key=k,
        )

        glyf[gname] = build_tt_glyph(contours)

        # Advance: (tight viewBox width + spacing) scaled by wdth + any extra adv from condensed strip compensation
        adv_svg_scaled = (float(width_svg) + LETTER_SPACING_SVG) * x_scale + extra_adv_svg
        adv = int(round(adv_svg_scaled * SCALE_BASE))
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
# Variable font builder (2-axis, 3x3 masters)
# -----------------------------
def build_variable_font() -> None:
    root = project_root()
    out_dir = root / "dist" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    masters_dir = out_dir / "_vf_masters"
    masters_dir.mkdir(parents=True, exist_ok=True)

    wdths = [WDTH_MIN, WDTH_DEF, WDTH_MAX]
    hghts = [HGHT_MIN, HGHT_DEF, HGHT_MAX]

    master_paths: Dict[Tuple[float, float], Path] = {}

    for w in wdths:
        for h in hghts:
            style = f"W{int(w)}H{int(h)}"
            p = masters_dir / f"unst-wdth{int(w)}-hght{int(h)}.ttf"
            build_master_ttf(out_path=p, style_name=style, wdth_value=w, hght_value=h)
            master_paths[(w, h)] = p
            print(f"Wrote master: {p}")

    # Designspace
    ds = DesignSpaceDocument()

    ax_w = AxisDescriptor()
    ax_w.tag = "wdth"
    ax_w.name = "Width"
    ax_w.minimum = WDTH_MIN
    ax_w.default = WDTH_DEF
    ax_w.maximum = WDTH_MAX
    ds.addAxis(ax_w)

    ax_h = AxisDescriptor()
    ax_h.tag = "hght"
    ax_h.name = "Height"
    ax_h.minimum = HGHT_MIN
    ax_h.default = HGHT_DEF
    ax_h.maximum = HGHT_MAX
    ds.addAxis(ax_h)

    for w in wdths:
        for h in hghts:
            s = SourceDescriptor()
            s.name = f"unst-W{int(w)}H{int(h)}"
            rel = master_paths[(w, h)].relative_to(out_dir).as_posix()
            s.filename = rel
            s.location = {"Width": w, "Height": h}
            if w == WDTH_DEF and h == HGHT_DEF:
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
