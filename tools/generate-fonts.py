#!/usr/bin/env python3
"""
Build UNST *variable* font from the SVG glyphs in ./src:

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

Outputs:
  dist/fonts/unst-variable.ttf
  dist/fonts/unst-variable.woff
  dist/fonts/unst-variable.woff2   (if brotli is available)

Axes:
  wdth: 25 .. 400 (default 100)
  hght: 25 .. 400 (default 100)

Key property (your request):
  - hght is applied via a GLOBAL piecewise-linear Y warp based on the shared grid:
      cap band   0..1
      x-height   9..10
      mid band   14..15
      baseline   19..20
      desc band  29..30
    Band thickness stays 1 unit; only the gaps between bands scale.
    This keeps all horizontal bands aligned across all glyphs at any hght value.

Also:
  - ligatures via GSUB 'liga': st, ch, ct, fi, ij, sh
  - adds default spacing between letters in the font (4 SVG units at wdth=100),
    scaled with wdth.

Requires:
  pip install fonttools
Optional:
  pip install brotli   (for woff2)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from dataclasses import dataclass

from fontTools.designspaceLib import (
    DesignSpaceDocument,
    AxisDescriptor,
    SourceDescriptor,
)
from fontTools.varLib import build as var_build

try:
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
except Exception as e:
    raise SystemExit("fontTools.feaLib is required (it ships with fonttools).") from e


# -----------------------------
# Project / IO
# -----------------------------
def project_root() -> Path:
    # Script lives in a subfolder => project root is exactly one directory above script folder
    return Path(__file__).resolve().parent.parent


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
# Metrics / coordinate systems
# -----------------------------
UPM = 1000

# Your SVG coordinate system (y down)
SVG_BASELINE_Y = 20.0
SVG_TOTAL_H = 30.0  # original viewBox height (your generator uses this)

# SVG -> font units
SCALE = UPM / SVG_TOTAL_H  # 33.333...

# Font "typo" metrics (keep normal line height at default)
ASCENT_BASE = int(round((SVG_BASELINE_Y - 0.0) * SCALE))           # ~667
DESCENT_BASE = -int(round((SVG_TOTAL_H - SVG_BASELINE_Y) * SCALE)) # ~-333
if ASCENT_BASE - DESCENT_BASE != UPM:
    ASCENT_BASE = UPM + DESCENT_BASE

# Win metrics to avoid clipping at max hght
HGHT_MIN, HGHT_DEF, HGHT_MAX = 25.0, 100.0, 400.0
WDTH_MIN, WDTH_DEF, WDTH_MAX = 25.0, 100.0, 400.0

# Default inter-letter spacing in SVG units (at wdth=100)
LETTER_SPACING_SVG = 4.0

# -----------------------------
# Height warp (GLOBAL grid-anchored)
# -----------------------------
# Breakpoints in SVG units (source)
SRC_Y = [0.0, 1.0, 9.0, 10.0, 14.0, 15.0, 19.0, 20.0, 29.0, 30.0]


def height_dst_breakpoints(scale: float) -> List[float]:
    """
    scale = hght_pct / 100.0, e.g. 0.25 .. 4.0

    Keeps band thicknesses (all 1 unit) constant, scales only the gaps.
    Anchors baseline band at 19..20 and baseline at y=20.
    """
    # Anchor baseline band
    y19, y20 = 19.0, 20.0

    # Scaled gaps (between 1-unit bands)
    gap_15_19 = 4.0 * scale   # 15 -> 19
    gap_10_14 = 4.0 * scale   # 10 -> 14
    gap_1_9   = 8.0 * scale   #  1 ->  9
    gap_20_29 = 9.0 * scale   # 20 -> 29

    # Upwards from baseline band
    y15 = y19 - gap_15_19
    y14 = y15 - 1.0
    y10 = y14 - gap_10_14
    y9  = y10 - 1.0
    y1  = y9  - gap_1_9
    y0  = y1  - 1.0

    # Downwards for descenders
    y29 = y20 + gap_20_29
    y30 = y29 + 1.0

    return [y0, y1, y9, y10, y14, y15, y19, y20, y29, y30]


def warp_y(y: float, scale: float) -> float:
    """Piecewise-linear map from SRC_Y to DST_Y (computed)."""
    dst = height_dst_breakpoints(scale)

    for i in range(len(SRC_Y) - 1):
        y0, y1 = SRC_Y[i], SRC_Y[i + 1]
        if y0 <= y <= y1:
            t = 0.0 if y1 == y0 else (y - y0) / (y1 - y0)
            return dst[i] + t * (dst[i + 1] - dst[i])

    # Extrapolate (should rarely happen)
    if y < SRC_Y[0]:
        y0, y1 = SRC_Y[0], SRC_Y[1]
        return dst[0] + (y - y0) * (dst[1] - dst[0]) / (y1 - y0)

    y0, y1 = SRC_Y[-2], SRC_Y[-1]
    return dst[-1] + (y - y1) * (dst[-1] - dst[-2]) / (y1 - y0)


# Compute Win metrics for max height so glyphs don't clip in common renderers
_ymin_max = min(height_dst_breakpoints(HGHT_MAX / 100.0))
_ymax_max = max(height_dst_breakpoints(HGHT_MAX / 100.0))
US_WIN_ASCENT = int(round((SVG_BASELINE_Y - _ymin_max) * SCALE))
US_WIN_DESCENT = int(round((_ymax_max - SVG_BASELINE_Y) * SCALE))


# -----------------------------
# SVG parsing (polygons only)
# -----------------------------
Point = Tuple[float, float]
Poly = List[Point]


def parse_polygon_points(points_str: str) -> Poly:
    pts: Poly = []
    for token in points_str.replace("\n", " ").replace("\t", " ").split():
        if not token.strip():
            continue
        x_s, y_s = token.split(",")
        pts.append((float(x_s), float(y_s)))
    if len(pts) < 3:
        raise ValueError(f"Polygon has too few points: {points_str!r}")
    return pts


def is_axis_aligned_rect(poly: Poly) -> Tuple[bool, float, float, float, float]:
    xs = sorted({p[0] for p in poly})
    ys = sorted({p[1] for p in poly})
    if len(poly) == 4 and len(xs) == 2 and len(ys) == 2:
        x0, x1 = xs[0], xs[1]
        y0, y1 = ys[0], ys[1]
        return True, x0, y0, x1, y1
    return False, 0.0, 0.0, 0.0, 0.0


@dataclass(frozen=True)
class SvgGlyph:
    width_svg: float
    polys: List[Poly]
    # per-poly reverse flags (computed once on default master) so point order stays identical across masters
    reverse_flags: List[bool]


def signed_area_xy_int(pts: List[Tuple[int, int]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def svg_to_font_xy(x_svg: float, y_svg: float) -> Tuple[int, int]:
    x = int(round(x_svg * SCALE))
    y = int(round((SVG_BASELINE_Y - y_svg) * SCALE))
    return x, y


def load_svg_polys(svg_path: Path) -> Tuple[float, List[Poly]]:
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.attrib.get("viewBox")
    if not vb:
        raise ValueError(f"No viewBox on {svg_path}")
    _, _, w_s, _h_s = vb.strip().split()
    width_svg = float(w_s)

    polys = root.findall(".//{http://www.w3.org/2000/svg}polygon")
    if not polys:
        polys = root.findall(".//polygon")
    if not polys:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    out: List[Poly] = []
    for p in polys:
        out.append(parse_polygon_points(p.attrib["points"]))

    return width_svg, out


def compute_reverse_flags_default(polys: List[Poly]) -> List[bool]:
    """
    Decide whether each contour should be reversed to become clockwise in font coords.
    Compute once at default (wdth=100, hght=100) and reuse for all masters so point order matches.
    """
    flags: List[bool] = []
    for poly in polys:
        pts_font = [svg_to_font_xy(x, y) for (x, y) in poly]
        # In font coords (y up), clockwise contours have negative signed area.
        flags.append(signed_area_xy_int(pts_font) > 0)
    return flags


# -----------------------------
# Transform polygons for masters
# -----------------------------
def transform_poly(poly: Poly, *, wdth_scale: float, hght_scale: float) -> Poly:
    """
    Apply:
      - width scaling in X (with special-case for 1-unit-wide vertical connector rectangles:
        keep them 1 unit wide, but position them according to scaled right edge)
      - global height warp in Y via warp_y()
    """
    is_rect, x0, y0, x1, y1 = is_axis_aligned_rect(poly)

    # width transform (X only)
    if is_rect:
        w = x1 - x0
        h = y1 - y0

        if abs(w - 1.0) < 1e-9 and h > 1.0:
            # Thin vertical connector: keep width == 1, anchor by its RIGHT edge
            nx1 = x1 * wdth_scale
            nx0 = nx1 - 1.0
        else:
            nx0 = x0 * wdth_scale
            nx1 = x1 * wdth_scale

        # height transform (Y warp)
        ny0 = warp_y(y0, hght_scale)
        ny1 = warp_y(y1, hght_scale)

        # Preserve rectangle point order as in R(x0,y0,x1,y1): (x0,y0),(x1,y0),(x1,y1),(x0,y1)
        return [(nx0, ny0), (nx1, ny0), (nx1, ny1), (nx0, ny1)]

    # General polygon (e.g. the custom 'st' polygon): point-wise transform
    out: Poly = []
    for (x, y) in poly:
        nx = x * wdth_scale
        ny = warp_y(y, hght_scale)
        out.append((nx, ny))
    return out


# -----------------------------
# OpenType features (liga)
# -----------------------------
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
# TT glyph construction
# -----------------------------
def build_tt_glyph_from_polys(polys_font: List[List[Tuple[int, int]]]) -> object:
    pen = TTGlyphPen(None)
    for contour in polys_font:
        if len(contour) < 3:
            continue
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


# -----------------------------
# Master font builder
# -----------------------------
def build_master_font(
    glyphs: Dict[str, SvgGlyph],
    *,
    wdth_value: float,
    hght_value: float,
    out_path: Path,
) -> None:
    wdth_scale = wdth_value / 100.0
    hght_scale = hght_value / 100.0

    keys: List[str] = []
    keys.extend(LETTERS)
    keys.extend(DIGITS)
    keys.extend(LIGATURE_KEYS)

    glyph_order: List[str] = [".notdef", "space"]
    for k in keys:
        glyph_order.append(key_to_glyph_name(k))

    glyf: Dict[str, object] = {".notdef": make_notdef_glyph()}
    hmtx: Dict[str, Tuple[int, int]] = {}

    # spacing scales with width axis
    spacing_adv = int(round((LETTER_SPACING_SVG * wdth_scale) * SCALE))

    # space: one base cell (12 SVG units) scaled, plus spacing
    space_adv = int(round((12.0 * wdth_scale) * SCALE)) + spacing_adv
    glyf["space"] = TTGlyphPen(None).glyph()
    hmtx["space"] = (space_adv, 0)
    hmtx[".notdef"] = (space_adv, 0)

    cmap: Dict[int, str] = {}
    for ch in LETTERS:
        cmap[ord(ch)] = ch
    for d in DIGITS:
        cmap[ord(d)] = DIGIT_GLYPH_NAMES[d]
    # Optional: U+0133 ĳ maps to ij glyph
    cmap[0x0133] = "ij"

    # Build glyphs
    for k in keys:
        gname = key_to_glyph_name(k)
        sg = glyphs[k]

        # transform each polygon
        tpolys: List[Poly] = [
            transform_poly(p, wdth_scale=wdth_scale, hght_scale=hght_scale)
            for p in sg.polys
        ]

        # convert to font coords (int) + apply the same reverse decision across masters
        contours_font: List[List[Tuple[int, int]]] = []
        for idx, poly in enumerate(tpolys):
            pts = [svg_to_font_xy(x, y) for (x, y) in poly]
            if sg.reverse_flags[idx]:
                pts = list(reversed(pts))
            contours_font.append(pts)

        glyf[gname] = build_tt_glyph_from_polys(contours_font)

        adv = int(round((sg.width_svg * wdth_scale) * SCALE)) + spacing_adv
        hmtx[gname] = (adv, 0)

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(hmtx)

    # Keep normal line height (typo metrics), but large Win metrics to avoid clipping
    fb.setupHorizontalHeader(ascent=ASCENT_BASE, descent=DESCENT_BASE)
    fb.setupOS2(
        sTypoAscender=ASCENT_BASE,
        sTypoDescender=DESCENT_BASE,
        usWinAscent=US_WIN_ASCENT,
        usWinDescent=US_WIN_DESCENT,
    )

    fb.setupNameTable(
        {
            "familyName": "unst",
            "styleName": "Regular",
            "uniqueFontIdentifier": "unst Variable Master",
            "fullName": "unst Variable Master",
            "psName": "unst-VariableMaster",
            "version": "Version 1.0",
        }
    )
    fb.setupPost()
    fb.setupMaxp()
    fb.setupHead()

    # Add GSUB ligatures into masters (varLib will carry them over)
    addOpenTypeFeaturesFromString(fb.font, build_fea_liga())

    fb.font.save(out_path)


# -----------------------------
# Variable font build
# -----------------------------
def build_variable_font() -> None:
    root = project_root()
    src_dir = root / "src"
    out_dir = root / "dist" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load SVG glyphs once
    keys = list("abcdefghijklmnopqrstuvwxyz0123456789") + LIGATURE_KEYS
    glyphs: Dict[str, SvgGlyph] = {}

    for k in keys:
        svg_path = src_dir / f"character-{k}.svg"
        if not svg_path.exists():
            raise FileNotFoundError(f"Missing SVG: {svg_path}")

        w_svg, polys = load_svg_polys(svg_path)
        reverse_flags = compute_reverse_flags_default(polys)
        glyphs[k] = SvgGlyph(width_svg=w_svg, polys=polys, reverse_flags=reverse_flags)

    # Master grid (only ONE default master at 100/100)
    wdths = [WDTH_MIN, WDTH_DEF, WDTH_MAX]
    hghts = [HGHT_MIN, HGHT_DEF, HGHT_MAX]
    master_locs: List[Tuple[float, float]] = [(w, h) for w in wdths for h in hghts]

    with tempfile.TemporaryDirectory(prefix="unst_var_masters_") as td:
        td_path = Path(td)

        # Build master TTFonts
        master_paths: Dict[Tuple[float, float], Path] = {}
        for w, h in master_locs:
            p = td_path / f"unst_master_w{int(w)}_h{int(h)}.ttf"
            build_master_font(glyphs, wdth_value=w, hght_value=h, out_path=p)
            master_paths[(w, h)] = p

        # Build designspace
        ds = DesignSpaceDocument()

        ax_w = AxisDescriptor()
        ax_w.name = "wdth"
        ax_w.tag = "wdth"
        ax_w.minimum = WDTH_MIN
        ax_w.default = WDTH_DEF
        ax_w.maximum = WDTH_MAX
        ds.addAxis(ax_w)

        ax_h = AxisDescriptor()
        ax_h.name = "hght"
        ax_h.tag = "hght"
        ax_h.minimum = HGHT_MIN
        ax_h.default = HGHT_DEF
        ax_h.maximum = HGHT_MAX
        ds.addAxis(ax_h)

        # Ensure the *only* base master is (100,100)
        default_loc = {"wdth": WDTH_DEF, "hght": HGHT_DEF}

        # Add sources; put default first for cleanliness
        ordered_locs = [(WDTH_DEF, HGHT_DEF)] + [loc for loc in master_locs if loc != (WDTH_DEF, HGHT_DEF)]
        for w, h in ordered_locs:
            src = SourceDescriptor()
            src.name = f"master_w{int(w)}_h{int(h)}"
            src.familyName = "unst"
            src.styleName = "Regular"
            src.filename = str(master_paths[(w, h)])
            src.location = {"wdth": float(w), "hght": float(h)}
            src.copyLib = (src.location == default_loc)
            src.copyInfo = (src.location == default_loc)
            src.copyGroups = (src.location == default_loc)
            src.copyFeatures = (src.location == default_loc)
            ds.addSource(src)

        ds_path = td_path / "unst.designspace"
        ds.write(ds_path)

        # Build variable font
        vf, _model, _master_ttfs = var_build(str(ds_path))
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
