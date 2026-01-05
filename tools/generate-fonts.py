#!/usr/bin/env python3
"""
Build UNST variable font from SVG polygons in ./src.

Key behaviors implemented:
- Axes: wdth (25..400, default 100), hght (25..400, default 100)
- Thick geometry scales with axes, BUT:
  - Any 1-unit-tall horizontal rectangles stay 1 unit tall under hght changes
  - Any 1-unit-wide vertical rectangles stay 1 unit wide under wdth changes
- For st-like ligatures (ch/sh/ct and also st even if st is one polygon):
  apply a seam compensation in X so the "gap" behaves like thick bars:
    x' = x*s              for x < seam
    x' = x*s + (1-s)      for x >= seam
  where seam is the connector's right edge (typically left.width).

Outputs:
  dist/fonts/unst-variable.ttf
  dist/fonts/unst-variable.woff
  dist/fonts/unst-variable.woff2  (if brotli is available)

Requires:
  pip install fonttools
Optional:
  pip install brotli  (for woff2)
"""
from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor
from fontTools.varLib import build as var_build

try:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
except Exception as e:
    raise SystemExit("fontTools.feaLib is required (it ships with fonttools).") from e


# -----------------------------
# Project paths
# -----------------------------
def project_root() -> Path:
    # script lives in a subfolder => project root is exactly one directory above script folder
    return Path(__file__).resolve().parent.parent


# -----------------------------
# Geometry / metrics (must match your SVG generator)
# -----------------------------
UPM = 1000

# SVG coordinate system (y down). Your design’s "baseline" is y=20.
SVG_BASELINE_Y = 20.0
SVG_BASE_H = 30.0  # base viewBox height in SVG units

# Scale SVG units -> font units
SCALE = UPM / SVG_BASE_H  # 33.333...

# Default letter spacing in SVG units (like your thick bar width)
LETTER_SPACE_SVG = 4.0

# Canonical bands (in SVG units) used to keep global alignment under hght changes
# These are the ones you derived earlier.
Y_CAP0,  Y_CAP1  = 0.0, 1.0
Y_TOP0,  Y_TOP1  = 9.0, 10.0
Y_MID0,  Y_MID1  = 14.0, 15.0
Y_BASE0, Y_BASE1 = 19.0, 20.0
Y_DESC0, Y_DESC1 = 29.0, 30.0


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
Poly = List[Point]


def parse_polygon_points(points_str: str) -> Poly:
    pts: List[Point] = []
    for token in points_str.replace("\n", " ").replace("\t", " ").split():
        if not token.strip():
            continue
        x_s, y_s = token.split(",")
        pts.append((float(x_s), float(y_s)))
    if len(pts) < 3:
        raise ValueError(f"Polygon has too few points: {points_str!r}")
    return pts


@dataclass
class SvgGlyph:
    width_svg: float
    polys: List[Poly]
    seam_x: Optional[float]  # for st-like ligature compensation


def is_axis_aligned_rect(poly: Poly) -> Optional[Tuple[float, float, float, float]]:
    """
    If poly is an axis-aligned rectangle (4 points), return (x0,y0,x1,y1) with x0<x1, y0<y1.
    """
    if len(poly) != 4:
        return None
    xs = sorted({p[0] for p in poly})
    ys = sorted({p[1] for p in poly})
    if len(xs) != 2 or len(ys) != 2:
        return None
    x0, x1 = xs
    y0, y1 = ys
    # Ensure all points are corners
    corners = {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
    if set(poly) != corners:
        # Some rectangles may list corners in another order but still match;
        # If it's the same set, accept.
        if set(poly) == corners:
            return (x0, y0, x1, y1)
        return None
    return (x0, y0, x1, y1)


def detect_seam_x(key: str, width_svg: float, polys: List[Poly]) -> Optional[float]:
    """
    Find seam_x for st-like ligatures by detecting the 1-unit-wide vertical connector rectangle.
    Seam is the RIGHT edge (x1) of that 1-unit rectangle.

    If not found:
      - for 'st' (which in your older SVG generator is a single polygon), fall back to seam=12
        because the design is 12 (s) + 4 gap + 8 (t) = 24, and the connector sits at x=11..12.
    """
    best: Optional[float] = None
    for poly in polys:
        r = is_axis_aligned_rect(poly)
        if not r:
            continue
        x0, y0, x1, y1 = r
        w = x1 - x0
        h = y1 - y0
        if abs(w - 1.0) < 1e-9 and h > 1.0:
            # choose the rightmost such rect (should be the connector)
            if best is None or x1 > best:
                best = x1

    if best is not None:
        return best

    if key == "st":
        # Your system: s width 12, connector in last column => seam at 12
        return 12.0

    return None


def load_svg_glyph(svg_path: Path, key: str) -> SvgGlyph:
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.attrib.get("viewBox")
    if not vb:
        raise ValueError(f"No viewBox on {svg_path}")
    _, _, w_s, _h_s = vb.strip().split()
    width_svg = float(w_s)

    # collect polygons
    polys = root.findall(".//{http://www.w3.org/2000/svg}polygon")
    if not polys:
        polys = root.findall(".//polygon")
    if not polys:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    poly_list: List[Poly] = []
    for p in polys:
        poly_list.append(parse_polygon_points(p.attrib["points"]))

    seam_x = detect_seam_x(key, width_svg, poly_list)

    return SvgGlyph(width_svg=width_svg, polys=poly_list, seam_x=seam_x)


# -----------------------------
# Axis warps
# -----------------------------
def wdth_scale_from_value(wdth_value: float) -> float:
    # axis values are 25..400, default 100
    return wdth_value / 100.0


def hght_scale_from_value(hght_value: float) -> float:
    return hght_value / 100.0


def warp_x(x: float, s: float, seam_x: Optional[float]) -> float:
    """
    X mapping with seam compensation for st-like ligatures.
    For seam glyphs:
      x' = x*s              if x < seam
      x' = x*s + (1-s)      if x >= seam
    """
    if seam_x is None:
        return x * s
    if x < seam_x:
        return x * s
    return x * s + (1.0 - s)


def warp_y_pos(y: float, t: float) -> float:
    """
    Piecewise Y warp that:
      - keeps the canonical 1-unit bands at [0..1], [9..10], [14..15], [19..20], [29..30] as bands
      - scales the spaces between them by factor t
    """
    # precompute mapped anchor positions
    y0 = 0.0
    y1 = 1.0
    y2 = y1 + (Y_TOP0 - Y_CAP1) * t  # start of 9..10 band
    y3 = y2 + 1.0                    # end of 9..10 band
    y4 = y3 + (Y_MID0 - Y_TOP1) * t  # start of 14..15 band
    y5 = y4 + 1.0                    # end of 14..15 band
    y6 = y5 + (Y_BASE0 - Y_MID1) * t # start of 19..20 band
    y7 = y6 + 1.0                    # end of 19..20 band
    y8 = y7 + (Y_DESC0 - Y_BASE1) * t# start of 29..30 band
    y9 = y8 + 1.0                    # end of 29..30 band

    if y < Y_CAP1:  # 0..1
        return y
    if y < Y_TOP0:  # 1..9
        return y1 + (y - Y_CAP1) * t
    if y < Y_TOP1:  # 9..10 band
        return y2 + (y - Y_TOP0)
    if y < Y_MID0:  # 10..14
        return y3 + (y - Y_TOP1) * t
    if y < Y_MID1:  # 14..15 band
        return y4 + (y - Y_MID0)
    if y < Y_BASE0: # 15..19
        return y5 + (y - Y_MID1) * t
    if y < Y_BASE1: # 19..20 band
        return y6 + (y - Y_BASE0)
    if y < Y_DESC0: # 20..29
        return y7 + (y - Y_BASE1) * t
    # 29..30 band
    if y <= Y_DESC1:
        return y8 + (y - Y_DESC0)
    # outside nominal (shouldn't happen)
    return y9 + (y - Y_DESC1) * t


def svg_to_font_xy(x_svg: float, y_svg: float, *, base_y_warped: float) -> Tuple[int, int]:
    """
    Convert warped SVG coords (y down) to font coords (y up) with baseline at 0.
    """
    x = int(round(x_svg * SCALE))
    y = int(round((base_y_warped - y_svg) * SCALE))
    return x, y


def signed_area_xy(pts: List[Tuple[int, int]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


# -----------------------------
# Transform polygons for a master
# -----------------------------
def transform_poly(poly: Poly, *, s: float, t: float, seam_x: Optional[float]) -> Poly:
    """
    Apply width+height transforms in SVG units.

    Special cases:
      - If poly is an axis-aligned rectangle with height==1: keep its height exactly 1 (horizontal thin stroke).
      - If poly is an axis-aligned rectangle with width==1: keep its width exactly 1 (vertical thin stroke).
    """
    r = is_axis_aligned_rect(poly)
    if r:
        x0, y0, x1, y1 = r
        w = x1 - x0
        h = y1 - y0

        # X edges
        nx0 = warp_x(x0, s, seam_x)
        if abs(w - 1.0) < 1e-9:
            # keep width 1, anchor at left edge
            nx1 = nx0 + 1.0
        else:
            nx1 = warp_x(x1, s, seam_x)

        # Y edges
        ny0 = warp_y_pos(y0, t)
        if abs(h - 1.0) < 1e-9:
            # keep height 1, anchor at top edge
            ny1 = ny0 + 1.0
        else:
            ny1 = warp_y_pos(y1, t)

        # Return as rect polygon (clockwise set)
        return [(nx0, ny0), (nx1, ny0), (nx1, ny1), (nx0, ny1)]

    # Generic polygon: pointwise mapping
    out: Poly = []
    for x, y in poly:
        out.append((warp_x(x, s, seam_x), warp_y_pos(y, t)))
    return out


# -----------------------------
# Build TT glyphs
# -----------------------------
def build_tt_glyph_from_polys(polys_svg_warped: List[Poly], *, base_y_warped: float) -> object:
    pen = TTGlyphPen(None)

    for poly in polys_svg_warped:
        pts_font = [svg_to_font_xy(x, y, base_y_warped=base_y_warped) for (x, y) in poly]
        # Ensure contour direction is consistent (clockwise in font coords => negative area)
        if signed_area_xy(pts_font) > 0:
            pts_font = list(reversed(pts_font))

        pen.moveTo(pts_font[0])
        for pt in pts_font[1:]:
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
# Master generation
# -----------------------------
def compute_global_vertical_metrics() -> Tuple[int, int]:
    """
    Compute ascent/descent to fit the maximum hght master (400%).
    """
    t_max = hght_scale_from_value(400.0)
    base_y = warp_y_pos(SVG_BASELINE_Y, t_max)
    top_y = warp_y_pos(0.0, t_max)
    bot_y = warp_y_pos(SVG_BASE_H, t_max)

    ascent_svg = base_y - top_y
    descent_svg = bot_y - base_y

    ascent = int(math.ceil(ascent_svg * SCALE))
    descent = -int(math.ceil(descent_svg * SCALE))
    return ascent, descent


def build_master_ttf(
    *,
    out_path: Path,
    glyph_svgs: Dict[str, SvgGlyph],
    wdth_value: float,
    hght_value: float,
) -> None:
    s = wdth_scale_from_value(wdth_value)
    t = hght_scale_from_value(hght_value)

    # baseline in warped SVG coords for this master
    base_y_warped = warp_y_pos(SVG_BASELINE_Y, t)

    # glyph order
    keys: List[str] = []
    keys.extend(LETTERS)
    keys.extend(DIGITS)
    keys.extend(LIGATURE_KEYS)

    glyph_order: List[str] = [".notdef", "space"] + [key_to_glyph_name(k) for k in keys]

    # cmap
    cmap: Dict[int, str] = {ord(ch): ch for ch in LETTERS}
    for d in DIGITS:
        cmap[ord(d)] = DIGIT_GLYPH_NAMES[d]
    # Optional U+0133 mapping to ij glyph
    cmap[0x0133] = "ij"

    # build glyf/hmtx
    glyf: Dict[str, object] = {".notdef": make_notdef_glyph()}
    hmtx: Dict[str, Tuple[int, int]] = {}

    # space width: one bar + spacing (tied to wdth like other advances)
    space_adv_svg = 12.0 + LETTER_SPACE_SVG
    space_adv_font = int(round((space_adv_svg * s) * SCALE))
    glyf["space"] = TTGlyphPen(None).glyph()
    hmtx["space"] = (space_adv_font, 0)
    hmtx[".notdef"] = (space_adv_font, 0)

    for k in keys:
        gname = key_to_glyph_name(k)
        sg = glyph_svgs[k]

        # transform polygons
        warped_polys = [transform_poly(p, s=s, t=t, seam_x=sg.seam_x) for p in sg.polys]
        glyf[gname] = build_tt_glyph_from_polys(warped_polys, base_y_warped=base_y_warped)

        # advance width: (viewBox width + letter space), then warped in X with same seam behavior
        adv_svg = sg.width_svg + LETTER_SPACE_SVG
        adv_warped = warp_x(adv_svg, s, sg.seam_x)
        adv_font = int(round(adv_warped * SCALE))
        hmtx[gname] = (adv_font, 0)

    # vertical metrics
    ASCENT, DESCENT = compute_global_vertical_metrics()

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
            "uniqueFontIdentifier": f"unst Regular wdth{int(wdth_value)} hght{int(hght_value)}",
            "fullName": "unst Regular",
            "psName": "unst-Regular",
            "version": "Version 1.0",
        }
    )
    fb.setupPost()
    fb.setupMaxp()
    fb.setupHead()

    # Add ligatures
    addOpenTypeFeaturesFromString(fb.font, build_fea_liga())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fb.font.save(out_path)


# -----------------------------
# Variable font build
# -----------------------------
def build_variable_font() -> None:
    root = project_root()
    src_dir = root / "src"
    out_dir = root / "dist" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load SVG glyphs
    keys: List[str] = []
    keys.extend(LETTERS)
    keys.extend(DIGITS)
    keys.extend(LIGATURE_KEYS)

    glyph_svgs: Dict[str, SvgGlyph] = {}
    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")
        glyph_svgs[k] = load_svg_glyph(svg_path, k)

    # Build a 3x3 grid of masters (robust for 2D var)
    wdths = [25.0, 100.0, 400.0]
    hghts = [25.0, 100.0, 400.0]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Write master TTFS
        master_paths: Dict[Tuple[float, float], Path] = {}
        for w in wdths:
            for h in hghts:
                p = td_path / f"unst-master-w{int(w)}-h{int(h)}.ttf"
                build_master_ttf(out_path=p, glyph_svgs=glyph_svgs, wdth_value=w, hght_value=h)
                master_paths[(w, h)] = p

        # Build designspace
        ds = DesignSpaceDocument()

        ax_w = AxisDescriptor()
        ax_w.tag = "wdth"
        ax_w.name = "wdth"
        ax_w.minimum = 25.0
        ax_w.default = 100.0
        ax_w.maximum = 400.0
        ds.addAxis(ax_w)

        ax_h = AxisDescriptor()
        ax_h.tag = "hght"
        ax_h.name = "hght"
        ax_h.minimum = 25.0
        ax_h.default = 100.0
        ax_h.maximum = 400.0
        ds.addAxis(ax_h)

        for (w, h), p in master_paths.items():
            src = SourceDescriptor()
            src.path = str(p)
            src.name = f"master_w{int(w)}_h{int(h)}"
            src.familyName = "unst"
            src.styleName = "Regular"
            src.location = {"wdth": w, "hght": h}
            # Only ONE default master at (100,100)
            src.copyLib = (w == 100.0 and h == 100.0)
            src.copyInfo = (w == 100.0 and h == 100.0)
            src.copyGroups = (w == 100.0 and h == 100.0)
            src.copyFeatures = (w == 100.0 and h == 100.0)
            ds.addSource(src)

        ds_path = td_path / "unst.designspace"
        ds.write(ds_path)

        # Build variable font
        vf, _model, _masters = var_build(str(ds_path))
        out_ttf = out_dir / "unst-variable.ttf"
        vf.save(out_ttf)
        print(f"Wrote: {out_ttf}")

        # Optional WOFF/WOFF2
        try:
            woff_font = TTFont(out_ttf)
            woff_font.flavor = "woff"
            woff_path = out_dir / "unst-variable.woff"
            woff_font.save(woff_path)
            print(f"Wrote: {woff_path}")
        except Exception as e:
            print(f"Skipping WOFF (error): {e}")

        try:
            woff2_font = TTFont(out_ttf)
            woff2_font.flavor = "woff2"
            woff2_path = out_dir / "unst-variable.woff2"
            woff2_font.save(woff2_path)
            print(f"Wrote: {woff2_path}")
        except Exception as e:
            print(f"Skipping WOFF2 (install 'brotli' to enable) (error): {e}")


if __name__ == "__main__":
    build_variable_font()
