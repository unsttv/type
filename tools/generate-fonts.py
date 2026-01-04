#!/usr/bin/env python3
"""
Build UNST variable font from SVG glyphs in ./src with two axes:

  wdth: 25 .. 400 (default 100)
  hght: 25 .. 400 (default 100)

Outputs:
  dist/fonts/unst-variable.ttf
  dist/fonts/unst-variable.woff
  dist/fonts/unst-variable.woff2   (if brotli is available)

Includes GSUB 'liga' substitutions for:
  st, ch, ct, fi, ij, sh

Stroke behavior:
  - thin vertical connector bars (1 SVG unit wide) do NOT scale in width (ligatures)
  - thin horizontal strokes (1 SVG unit tall) do NOT scale in height (all glyphs)
  - IMPORTANT: thin stroke thickness is enforced in FONT UNITS
  - IMPORTANT: edges that TOUCH thin horizontals are Y-SNAPPED globally per glyph
               (fixes n/u/ch etc at high hght)

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
# Geometry / metrics
# -----------------------------
UPM = 1000

SVG_BASELINE_Y = 20.0
SVG_TOTAL_H = 30.0

SCALE_BASE = UPM / SVG_TOTAL_H  # 33.333...
THIN_FU = int(round(1.0 * SCALE_BASE))  # 1 SVG unit in font units (constant thickness)

LETTER_SPACING_SVG = 4.0  # scales with wdth

# Axis limits
WDTH_MIN, WDTH_DEF, WDTH_MAX = 25.0, 100.0, 400.0
HGHT_MIN, HGHT_DEF, HGHT_MAX = 25.0, 100.0, 400.0

# Vertical metrics large enough for max height (scale about baseline)
MAX_Y_SCALE = HGHT_MAX / 100.0
TOP_Y_AT_MAX = SVG_BASELINE_Y + (0.0 - SVG_BASELINE_Y) * MAX_Y_SCALE      # -60
BOT_Y_AT_MAX = SVG_BASELINE_Y + (SVG_TOTAL_H - SVG_BASELINE_Y) * MAX_Y_SCALE  # 60

ASCENT = int(round((SVG_BASELINE_Y - TOP_Y_AT_MAX) * SCALE_BASE))         # ~2667
DESCENT = -int(round((BOT_Y_AT_MAX - SVG_BASELINE_Y) * SCALE_BASE))       # ~-1333

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


# -----------------------------
# SVG parsing helpers
# -----------------------------
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


def bbox_svg(pts: List[Point]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


def scale_y_about_baseline(y_svg: float, y_scale: float) -> float:
    return SVG_BASELINE_Y + (y_svg - SVG_BASELINE_Y) * y_scale


def y_font_from_svg(y_svg: float, y_scale: float) -> int:
    """Convert SVG y (down) to font y (up), scaling about baseline."""
    y_eff = scale_y_about_baseline(y_svg, y_scale)
    return int(round((SVG_BASELINE_Y - y_eff) * SCALE_BASE))


def is_thin_vertical_connector(minx: float, maxx: float, miny: float, maxy: float) -> bool:
    w = maxx - minx
    h = maxy - miny
    if abs(w - 1.0) > EPS:
        return False
    if h < 9.0 - EPS:
        return False
    if miny > 0.01:
        return False
    return True


def find_internal_thin_vstrip_for_st(pts_svg: List[Point]) -> Optional[Tuple[float, float]]:
    """
    'st' is a single polygon. Find an internal x pair (x, x+1) in upper zone (y<=10.1)
    that's top-anchored and tall.
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


def y_key(y: float) -> int:
    # y-values are integral in your system, but keep this robust
    return int(round(y * 1000.0))


def transform_x(
    x_svg: float,
    *,
    x_scale: float,
    right_threshold: Optional[float],
    right_shift: float,
) -> float:
    x_eff = x_svg * x_scale
    if right_threshold is not None and right_shift > 0.0 and x_svg >= right_threshold - EPS:
        x_eff += right_shift
    return x_eff


# -----------------------------
# Build per-glyph Y snapping table for thin horizontals
# -----------------------------
def build_y_snap(
    polys_svg: List[List[Point]],
    *,
    y_scale: float,
    glyph_key: str,
) -> Dict[int, int]:
    """
    Find all 1-unit-tall horizontal bands (from bbox) and build a snapping table that:
      - keeps band thickness = THIN_FU
      - anchors the *structural* edge (whichever is referenced more by non-thin polygons)
      - snaps ANY point at y=y0 or y=y1 (even in other polygons), fixing joins.
    """
    thin_band_indices: List[int] = []
    bands: List[Tuple[float, float]] = []

    for i, pts in enumerate(polys_svg):
        _minx, _maxx, miny, maxy = bbox_svg(pts)
        if abs((maxy - miny) - 1.0) < EPS:
            thin_band_indices.append(i)
            bands.append((miny, maxy))

    # 'st' has no separate thin rectangles; add the canonical system bands if present
    if glyph_key == "st":
        # Use these only if the y-values exist in the polygon
        yset = {y_key(y) for (_x, y) in polys_svg[0]}
        for (y0, y1) in [(0.0, 1.0), (9.0, 10.0), (14.0, 15.0), (19.0, 20.0)]:
            if y_key(y0) in yset and y_key(y1) in yset:
                bands.append((y0, y1))

    # Count y usage in NON-thin polygons (indicates which edge is structural)
    usage: Dict[int, int] = {}
    for i, pts in enumerate(polys_svg):
        if i in thin_band_indices:
            continue
        for (_x, y) in pts:
            ky = y_key(y)
            usage[ky] = usage.get(ky, 0) + 1

    snap: Dict[int, int] = {}

    # Process bands in a stable order (top->bottom) so shared edges resolve nicely
    bands_sorted = sorted(set(bands), key=lambda t: (t[0], t[1]))

    for (y0, y1) in bands_sorted:
        k0, k1 = y_key(y0), y_key(y1)

        # If one side already resolved, anchor to it to keep consistency
        if k0 in snap and k1 in snap:
            continue
        if k0 in snap and k1 not in snap:
            snap[k1] = snap[k0] - THIN_FU
            continue
        if k1 in snap and k0 not in snap:
            snap[k0] = snap[k1] + THIN_FU
            continue

        c0 = usage.get(k0, 0)
        c1 = usage.get(k1, 0)

        # Decide anchor edge
        # - if one side referenced more, anchor that side
        # - tie: cap band prefers top edge (y0==0), otherwise prefer bottom edge
        if c0 > c1:
            anchor = "y0"
        elif c1 > c0:
            anchor = "y1"
        else:
            anchor = "y0" if abs(y0 - 0.0) < EPS else "y1"

        if anchor == "y0":
            y0_font = y_font_from_svg(y0, y_scale)
            y1_font = y0_font - THIN_FU
        else:
            y1_font = y_font_from_svg(y1, y_scale)
            y0_font = y1_font + THIN_FU

        snap[k0] = y0_font
        snap[k1] = y1_font

    return snap


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
    y_snap: Dict[int, int],
) -> IntPoint:
    # ---- Y: snap if this y is part of any thin horizontal band in this glyph ----
    ky = y_key(y_svg)
    if ky in y_snap:
        y_font = y_snap[ky]
    else:
        y_font = y_font_from_svg(y_svg, y_scale)

    # ---- X: normal scaling + condensed compensation ----
    x_eff = transform_x(
        x_svg,
        x_scale=x_scale,
        right_threshold=right_threshold,
        right_shift=right_shift,
    )
    x_font = int(round(x_eff * SCALE_BASE))

    # ---- X: freeze thin vertical connector WIDTH in font units ----
    if frozen_vstrip is not None:
        xL, xR = frozen_vstrip
        if (not vstrip_upper_only) or (y_svg <= 10.1 + EPS):
            if abs(x_svg - xL) < EPS:
                xL_font = int(round((xL * x_scale) * SCALE_BASE))
                x_font = xL_font
            elif abs(x_svg - xR) < EPS:
                xL_font = int(round((xL * x_scale) * SCALE_BASE))
                x_font = xL_font + THIN_FU

    return x_font, y_font


# -----------------------------
# SVG -> contours loader
# -----------------------------
def load_svg_glyph(
    svg_path: Path,
    *,
    x_scale: float,
    y_scale: float,
    glyph_key: str,
) -> Tuple[int, List[List[IntPoint]], float]:
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

    # Preserve SVG polygon order exactly
    polys_svg: List[List[Point]] = [parse_polygon_points(p.attrib["points"]) for p in polys_el]

    # Build per-glyph y snapping table (critical fix)
    y_snap = build_y_snap(polys_svg, y_scale=y_scale, glyph_key=glyph_key)

    # Detect thin vertical connector polygon (if present) to freeze WIDTH
    vstrip: Optional[Tuple[float, float]] = None
    thin_v_poly_index: Optional[int] = None
    for idx, pts in enumerate(polys_svg):
        minx, maxx, miny, maxy = bbox_svg(pts)
        if is_thin_vertical_connector(minx, maxx, miny, maxy):
            vstrip = (minx, maxx)
            thin_v_poly_index = idx
            break

    # Special: st may have internal thin v-strip within its single polygon
    vstrip_upper_only = False
    if glyph_key == "st" and vstrip is None:
        vv = find_internal_thin_vstrip_for_st(polys_svg[0])
        if vv is not None:
            vstrip = vv
            vstrip_upper_only = True

    # Condensed spacing compensation for frozen vertical strip (wdth < 100%)
    right_shift = 0.0
    right_threshold: Optional[float] = None
    extra_advance_svg = 0.0

    if vstrip is not None and x_scale < 1.0 - EPS:
        right_shift = 1.0 - x_scale
        extra_advance_svg = right_shift

        xL, xR = vstrip

        if glyph_key == "st":
            xs = sorted({x for (x, _y) in polys_svg[0]})
            candidates = [x for x in xs if x > (xR + 1.0 + EPS)]
            right_threshold = min(candidates) if candidates else (xR + 1.0 + EPS)
        else:
            starts: List[float] = []
            for i, pts in enumerate(polys_svg):
                if thin_v_poly_index is not None and i == thin_v_poly_index:
                    continue
                minx, _maxx, _miny, _maxy = bbox_svg(pts)
                if minx > xR + EPS:
                    starts.append(minx)
            right_threshold = min(starts) if starts else (xR + 1.0 + EPS)

    contours: List[List[IntPoint]] = []
    for pts_svg in polys_svg:
        pts_font = [
            svg_to_font_xy(
                x, y,
                x_scale=x_scale,
                y_scale=y_scale,
                right_threshold=right_threshold,
                right_shift=right_shift,
                frozen_vstrip=vstrip,
                vstrip_upper_only=vstrip_upper_only,
                y_snap=y_snap,
            )
            for (x, y) in pts_svg
        ]
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

    # space advance: (12 + spacing) scaled by wdth
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

        # Advance: (tight viewBox width + spacing) scaled by wdth + extra shift if applied
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
    if masters_dir.exists():
        for p in masters_dir.glob("*.ttf"):
            p.unlink()
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
