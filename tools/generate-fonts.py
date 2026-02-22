#!/usr/bin/env python3
"""
Build UNST variable font from:
- Single glyph geometry in data/glyphs.py
- Ligature SVGs in ./src (ligature-uXXXX-uYYYY.svg)

Key behaviors implemented:
- Axes: wdth (25..400, default 100), hght (25..400, default 100)
- Thick geometry scales with axes, BUT:
  - canonical 1-unit horizontal bands stay 1 unit tall under hght changes (piecewise Y warp)
  - seam compensation keeps the seam connector column 1 unit wide under wdth changes
- For seam-bearing ligatures:
  apply seam compensation in X so the seam column stays 1 unit:
    x' = x*s              for x < seam
    x' = x*s + (1-s)      for x >= seam
  plus a generalized seam-adjacent horizontal-edge correction:
    horizontal edges that terminate on the seam get their left side shifted too
    (but NOT the seam connector column itself), so seam-adjacent "s" arms don't
    distort and the 1-unit connector stays 1 unit wide for wdth<100 and wdth>100.

Ligatures:
- Discovered from src/ by scanning files matching: ligature-u*.svg
- Filename defines the sequence:
    ligature-u0073-u0074.svg -> "st"
    ligature-u0066-u0069.svg -> "fi"
- GSUB liga rules are auto-generated from discovered ligatures, but only emitted
  when all component glyphs exist.

Optional (recommended):
- Shapely union of polygons before master generation to prevent tiny seams:
  pip install shapely

Build artifacts:
- Masters + designspace: build/fonts/_vf_masters/

Outputs:
- dist/fonts/unst.ttf
- dist/fonts/unst.woff
- dist/fonts/unst.woff2 (if brotli available)
- dist/fonts/unst.css    (copied from src/style/main.css)
"""
from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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

# ---- Optional: shapely for polygon union (recommended) ----
try:
    from shapely.geometry import Polygon as ShpPolygon
    from shapely.ops import unary_union as shp_unary_union
    _HAVE_SHAPELY = True
except Exception:
    _HAVE_SHAPELY = False

# Toggle: keep ON to prevent seams (uses shapely if available)
COMBINE_SHAPES = True

EPS = 1e-9
ROW_EPS = 1e-6  # tolerance for matching seam-fix rows

# -----------------------------
# Project paths
# -----------------------------
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


# -----------------------------
# Geometry / metrics (must match your design system)
# -----------------------------
UPM = 1000

# SVG coordinate system (y down). Design baseline is y=20.
SVG_BASELINE_Y = 20.0
SVG_BASE_H = 30.0

# Scale SVG units -> font units
SCALE = UPM / SVG_BASE_H

# Default letter spacing in SVG units
LETTER_SPACE_SVG = 4.0

# Canonical horizontal bands (in SVG units)
Y_CAP0,  Y_CAP1  = 0.0, 1.0
Y_TOP0,  Y_TOP1  = 9.0, 10.0
Y_MID0,  Y_MID1  = 14.0, 15.0
Y_BASE0, Y_BASE1 = 19.0, 20.0
Y_DESC0, Y_DESC1 = 29.0, 30.0


# -----------------------------
# Digit naming
# -----------------------------
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


def char_to_glyph_name(ch: str) -> str:
    """Stable glyph naming for singles loaded from data/glyphs.py."""
    if ch == " ":
        return "space"
    if ch in DIGIT_GLYPH_NAMES:
        return DIGIT_GLYPH_NAMES[ch]
    if len(ch) == 1 and (("a" <= ch <= "z") or ("A" <= ch <= "Z")):
        return ch

    cp = ord(ch)
    if cp <= 0xFFFF:
        return f"uni{cp:04X}"
    return f"u{cp:X}"


# -----------------------------
# CSS copy helper
# -----------------------------
def write_unst_css(*, root: Path, out_dir: Path) -> None:
    src_css = root / "src" / "style" / "main.css"
    out_css = out_dir / "unst.css"

    if not src_css.exists():
        raise FileNotFoundError(f"Missing CSS source file: {src_css}")

    out_dir.mkdir(parents=True, exist_ok=True)

    css_text = src_css.read_text(encoding="utf-8")
    if css_text and not css_text.endswith("\n"):
        css_text += "\n"

    out_css.write_text(css_text, encoding="utf-8")
    print(f"Wrote: {out_css}")


# -----------------------------
# Geometry types
# -----------------------------
Point = Tuple[float, float]
Poly = List[Point]


@dataclass(frozen=True)
class Ring:
    pts: Poly
    is_hole: bool


@dataclass
class SvgGlyph:
    width_svg: float
    rings: List[Ring]
    seam_x: Optional[float]
    seam_fix_rows: List[Tuple[float, float]]  # (x0, y_row)
    key: str  # debug / seam-logic key


@dataclass(frozen=True)
class SingleGlyph:
    char: str
    codepoint: int
    glyph_name: str
    geom: SvgGlyph


@dataclass(frozen=True)
class LigatureDef:
    key: str                 # e.g. "st"
    codepoints: List[int]    # e.g. [0x73, 0x74]
    glyph_name: str          # usually "st", fallback if unsafe
    svg_path: Path
    geom: SvgGlyph


# -----------------------------
# Shared polygon helpers
# -----------------------------
def _flatten_polygons(geom) -> Iterable["ShpPolygon"]:
    if geom is None:
        return
    gtype = getattr(geom, "geom_type", "")
    if gtype == "Polygon":
        yield geom
    elif gtype == "MultiPolygon":
        for g in geom.geoms:
            yield g
    elif gtype == "GeometryCollection":
        for g in geom.geoms:
            yield from _flatten_polygons(g)


def _shapely_union_to_rings(polys: List[Poly]) -> List[Ring]:
    shp_polys = []
    for p in polys:
        try:
            shp_polys.append(ShpPolygon(p))
        except Exception:
            shp_polys.append(ShpPolygon(p).buffer(0))

    u = shp_unary_union(shp_polys)
    rings: List[Ring] = []

    for poly in _flatten_polygons(u):
        ext = list(poly.exterior.coords)
        if len(ext) >= 2 and ext[0] == ext[-1]:
            ext = ext[:-1]
        rings.append(Ring([(float(x), float(y)) for (x, y) in ext], is_hole=False))

        for interior in poly.interiors:
            inn = list(interior.coords)
            if len(inn) >= 2 and inn[0] == inn[-1]:
                inn = inn[:-1]
            rings.append(Ring([(float(x), float(y)) for (x, y) in inn], is_hole=True))

    if not rings:
        return [Ring(p, False) for p in polys]

    return rings


def rings_from_polys(polys: List[Poly]) -> List[Ring]:
    if not polys:
        return []

    if COMBINE_SHAPES and _HAVE_SHAPELY:
        return _shapely_union_to_rings(polys)

    if COMBINE_SHAPES and not _HAVE_SHAPELY:
        print(
            "[warn] shapely not installed -> not combining shapes (you may see tiny seams). "
            "Install with: pip install shapely"
        )
    return [Ring(p, False) for p in polys]


# -----------------------------
# data/glyphs.py loading (singles)
# -----------------------------
def load_data_module(data_py_path: Path):
    if not data_py_path.exists():
        raise FileNotFoundError(
            f"Missing glyph data file: {data_py_path}\n"
            "Run tools/generate-data.py first."
        )

    spec = importlib.util.spec_from_file_location("unst_glyph_data", str(data_py_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {data_py_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _poly_from_data(poly_data) -> Poly:
    return [(float(x), float(y)) for (x, y) in poly_data]


def load_single_glyphs_from_data(data_py_path: Path) -> List[SingleGlyph]:
    mod = load_data_module(data_py_path)

    data = getattr(mod, "DATA", None)
    if not isinstance(data, dict):
        raise RuntimeError(f"{data_py_path} does not expose DATA dict")

    glyphs = data.get("glyphs")
    if not isinstance(glyphs, dict):
        raise RuntimeError(f"{data_py_path} DATA['glyphs'] missing or invalid")

    singles: List[SingleGlyph] = []

    for _u_key, rec in glyphs.items():
        if not isinstance(rec, dict):
            continue

        ch = rec.get("key")
        cp = rec.get("codepointInt")
        width = rec.get("width")
        polys_data = rec.get("polys", [])

        if not isinstance(ch, str) or len(ch) != 1:
            # data/glyphs.py should only contain single-codepoint glyphs
            continue
        if not isinstance(cp, int):
            continue
        if width is None:
            raise RuntimeError(f"Glyph record for U+{cp:04X} missing width")

        polys: List[Poly] = []
        for p in polys_data:
            polys.append(_poly_from_data(p))

        rings = rings_from_polys(polys)
        geom = SvgGlyph(
            width_svg=float(width),
            rings=rings,
            seam_x=None,
            seam_fix_rows=[],
            key=ch,
        )

        singles.append(
            SingleGlyph(
                char=ch,
                codepoint=cp,
                glyph_name=char_to_glyph_name(ch),
                geom=geom,
            )
        )

    singles.sort(key=lambda g: g.codepoint)

    # Detect glyph-name collisions (rare, but better to fail loudly)
    seen_names: Dict[str, SingleGlyph] = {}
    for g in singles:
        if g.glyph_name in seen_names:
            prev = seen_names[g.glyph_name]
            raise RuntimeError(
                f"Glyph name collision: {g.glyph_name!r} for "
                f"U+{prev.codepoint:04X} and U+{g.codepoint:04X}"
            )
        seen_names[g.glyph_name] = g

    return singles


# -----------------------------
# Ligature discovery from src/
# -----------------------------
LIGATURE_FILE_RE = re.compile(
    r"^ligature-((?:u[0-9a-fA-F]{1,8})(?:-u[0-9a-fA-F]{1,8})+)\.svg$"
)

SAFE_LIGA_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def parse_ligature_filename(name: str) -> Optional[Tuple[str, List[int]]]:
    """
    ligature-u0073-u0074.svg -> ("st", [0x73, 0x74])
    """
    m = LIGATURE_FILE_RE.match(name)
    if not m:
        return None
    parts = m.group(1).split("-")
    cps: List[int] = []
    chars: List[str] = []
    for part in parts:
        if not part.lower().startswith("u"):
            return None
        cp = int(part[1:], 16)
        cps.append(cp)
        try:
            chars.append(chr(cp))
        except ValueError:
            return None
    return ("".join(chars), cps)


def ligature_key_to_glyph_name(key: str, cps: List[int]) -> str:
    """
    Prefer literal key (st, fi, ij, ...) when safe as a glyph name.
    Otherwise fallback to a stable ASCII name.
    """
    if SAFE_LIGA_NAME_RE.fullmatch(key):
        return key
    # stable fallback
    return "liga_" + "_".join(f"u{cp:04X}" if cp <= 0xFFFF else f"u{cp:X}" for cp in cps)


def discover_ligatures(src_dir: Path) -> List[Tuple[str, List[int], Path]]:
    """
    Returns list of (key, cps, svg_path) for all ligature-u*.svg found.
    """
    found: List[Tuple[str, List[int], Path]] = []
    for p in sorted(src_dir.glob("ligature-u*.svg"), key=lambda x: x.name.lower()):
        parsed = parse_ligature_filename(p.name)
        if not parsed:
            continue
        key, cps = parsed
        found.append((key, cps, p))
    return found


# -----------------------------
# Ligature SVG parsing
# -----------------------------
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


def is_axis_aligned_rect(poly: Poly) -> Optional[Tuple[float, float, float, float]]:
    if len(poly) != 4:
        return None
    xs = sorted({p[0] for p in poly})
    ys = sorted({p[1] for p in poly})
    if len(xs) != 2 or len(ys) != 2:
        return None
    x0, x1 = xs
    y0, y1 = ys
    corners = {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
    if set(poly) != corners:
        return None
    return (x0, y0, x1, y1)


def detect_seam_x(key: str, polys: List[Poly]) -> Optional[float]:
    """
    Find seam_x for seam-bearing ligatures by detecting the 1-unit-wide vertical connector rectangle.
    Seam is the RIGHT edge (x1) of that 1-unit rectangle.

    If not found:
      - for 'st' (often a single polygon), fall back to seam=12
    """
    best: Optional[float] = None
    for poly in polys:
        r = is_axis_aligned_rect(poly)
        if not r:
            continue
        x0, y0, x1, y1 = r
        w = x1 - x0
        h = y1 - y0
        if abs(w - 1.0) < EPS and h > 1.0:
            if best is None or x1 > best:
                best = x1

    if best is not None:
        return best
    if key == "st":
        return 12.0
    return None


def detect_seam_fix_rows(
    key: str,
    seam_x: Optional[float],
    polys: List[Poly],
) -> List[Tuple[float, float]]:
    """
    Detect seam-adjacent horizontal edges that end on the seam.

    We store rows as (x0, y_row), meaning:
      on that exact y row, points with x in [x0, seam_x) are candidates for the
      extra seam offset. In warp_x we intentionally exclude the final connector unit
      [seam_x-1, seam_x) so the seam connector remains 1 unit wide.

    This works for both:
    - separate rectangles
    - merged/unioned one-polygon glyph outlines
    """
    if seam_x is None:
        return []

    rows: List[Tuple[float, float]] = []

    for poly in polys:
        n = len(poly)
        if n < 2:
            continue

        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]

            # Horizontal edge
            if abs(y1 - y2) > EPS:
                continue

            y = y1
            xa = min(x1, x2)
            xb = max(x1, x2)
            w = xb - xa

            # Horizontal runs terminating at seam, but not the seam connector's own 1-unit edge.
            if w <= 1.0 + EPS:
                continue
            if abs(xb - seam_x) > EPS:
                continue
            if xa >= seam_x - EPS:
                continue

            rows.append((xa, y))

    # De-dup float-safely
    dedup: List[Tuple[float, float]] = []
    for x0, y in rows:
        if not any(abs(x0 - dx0) < EPS and abs(y - dy) < EPS for dx0, dy in dedup):
            dedup.append((x0, y))

    # Conservative fallback for merged/hand-drawn 's' forms if no explicit seam-adjacent
    # horizontal edge is detectable. Row-based (not broad-band) to avoid seam skew.
    if not dedup and ("s" in key):
        dedup.extend([
            (seam_x - 4.0, Y_MID1),
            (seam_x - 4.0, Y_BASE0),
        ])

    return dedup


def load_ligature_svg(svg_path: Path, key: str) -> SvgGlyph:
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.attrib.get("viewBox")
    if not vb:
        raise ValueError(f"No viewBox on {svg_path}")
    parts = vb.strip().split()
    if len(parts) != 4:
        raise ValueError(f"Invalid viewBox on {svg_path}: {vb!r}")
    _, _, w_s, _h_s = parts
    width_svg = float(w_s)

    polys = root.findall(".//{http://www.w3.org/2000/svg}polygon")
    if not polys:
        polys = root.findall(".//polygon")
    if not polys:
        raise ValueError(f"No <polygon> elements found in {svg_path}")

    poly_list: List[Poly] = [parse_polygon_points(p.attrib["points"]) for p in polys]
    seam_x = detect_seam_x(key, poly_list)
    seam_fix_rows = detect_seam_fix_rows(key, seam_x, poly_list)
    rings = rings_from_polys(poly_list)

    return SvgGlyph(
        width_svg=width_svg,
        rings=rings,
        seam_x=seam_x,
        seam_fix_rows=seam_fix_rows,
        key=key,
    )


def load_ligatures_from_src(src_dir: Path) -> List[LigatureDef]:
    discovered = discover_ligatures(src_dir)
    ligs: List[LigatureDef] = []

    # de-dup by key (prefer first in sorted order)
    seen: set[str] = set()

    for key, cps, path in discovered:
        if key in seen:
            print(f"[warn] duplicate ligature key {key!r} from {path.name}; skipping")
            continue
        seen.add(key)

        gname = ligature_key_to_glyph_name(key, cps)
        geom = load_ligature_svg(path, key)
        ligs.append(LigatureDef(key=key, codepoints=cps, glyph_name=gname, svg_path=path, geom=geom))

    # sort by (len, codepoints) for stability
    ligs.sort(key=lambda l: (len(l.codepoints), tuple(l.codepoints)))
    return ligs


# -----------------------------
# Axis warps
# -----------------------------
def wdth_scale_from_value(wdth_value: float) -> float:
    return wdth_value / 100.0


def hght_scale_from_value(hght_value: float) -> float:
    return hght_value / 100.0


def warp_x(
    x: float,
    s: float,
    seam_x: Optional[float],
    *,
    seam_fix_rows: Optional[List[Tuple[float, float]]],
    key: str,
    y: Optional[float],
) -> float:
    """
    X mapping with seam compensation for seam-bearing ligatures.

    Base seam behavior:
      x' = x*s              if x < seam
      x' = x*s + (1-s)      if x >= seam

    Additional correction:
      On seam-adjacent horizontal rows, points LEFT of the seam connector column
      get the seam offset too. We intentionally exclude [seam-1, seam) so the
      seam connector itself stays exactly 1 unit wide.
    """
    if seam_x is None:
        return x * s

    seam_off = (1.0 - s)
    base = x * s if x < seam_x else (x * s + seam_off)

    if y is not None and seam_fix_rows:
        connector_left = seam_x - 1.0
        for x0, y_row in seam_fix_rows:
            if abs(y - y_row) <= ROW_EPS:
                # Shift only the part left of the connector column.
                if (x >= x0 - EPS) and (x < connector_left - EPS):
                    base += seam_off
                    break

    return base


def warp_y_pos(y: float, t: float) -> float:
    """
    Piecewise Y warp that keeps canonical 1-unit bands:
      [0..1], [9..10], [14..15], [19..20], [29..30]
    and scales the gaps between them by factor t.
    """
    y0 = 0.0
    y1 = 1.0
    y2 = y1 + (Y_TOP0 - Y_CAP1) * t
    y3 = y2 + 1.0
    y4 = y3 + (Y_MID0 - Y_TOP1) * t
    y5 = y4 + 1.0
    y6 = y5 + (Y_BASE0 - Y_MID1) * t
    y7 = y6 + 1.0
    y8 = y7 + (Y_DESC0 - Y_BASE1) * t
    y9 = y8 + 1.0

    if y < Y_CAP1:
        return y
    if y < Y_TOP0:
        return y1 + (y - Y_CAP1) * t
    if y < Y_TOP1:
        return y2 + (y - Y_TOP0)
    if y < Y_MID0:
        return y3 + (y - Y_TOP1) * t
    if y < Y_MID1:
        return y4 + (y - Y_MID0)
    if y < Y_BASE0:
        return y5 + (y - Y_MID1) * t
    if y < Y_BASE1:
        return y6 + (y - Y_BASE0)
    if y < Y_DESC0:
        return y7 + (y - Y_BASE1) * t
    if y <= Y_DESC1:
        return y8 + (y - Y_DESC0)
    return y9 + (y - Y_DESC1) * t


def svg_to_font_xy(x_svg: float, y_svg: float, *, base_y_warped: float) -> Tuple[int, int]:
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


def transform_ring(
    ring: Ring,
    *,
    s: float,
    t: float,
    seam_x: Optional[float],
    seam_fix_rows: Optional[List[Tuple[float, float]]],
    key: str,
) -> Ring:
    out: Poly = []
    for x, y in ring.pts:
        out.append(
            (
                warp_x(
                    x,
                    s,
                    seam_x,
                    seam_fix_rows=seam_fix_rows,
                    key=key,
                    y=y,
                ),
                warp_y_pos(y, t),
            )
        )
    return Ring(out, ring.is_hole)


# -----------------------------
# Build TT glyphs
# -----------------------------
def build_tt_glyph_from_rings(rings_svg_warped: List[Ring], *, base_y_warped: float) -> object:
    pen = TTGlyphPen(None)

    if not rings_svg_warped:
        return pen.glyph()

    for ring in rings_svg_warped:
        if not ring.pts:
            continue
        pts_font = [svg_to_font_xy(x, y, base_y_warped=base_y_warped) for (x, y) in ring.pts]
        if len(pts_font) < 3:
            continue

        area = signed_area_xy(pts_font)

        # In font coords (y up):
        #  - outer contours should be clockwise -> negative area
        #  - hole contours should be counter-clockwise -> positive area
        if ring.is_hole:
            if area < 0:
                pts_font = list(reversed(pts_font))
        else:
            if area > 0:
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


def build_fea_liga(ligatures: List[LigatureDef], available_glyph_names: set[str]) -> str:
    """
    Auto-generate liga rules based on discovered ligatures.

    For each ligature key (e.g. "st"), emit:
      sub s t by st;

    Only if:
      - all component glyph names exist
      - the ligature glyph name exists
    """
    rules: List[str] = []

    for lig in ligatures:
        comps = [char_to_glyph_name(ch) for ch in lig.key]
        out = lig.glyph_name

        if out not in available_glyph_names:
            continue
        if any(cn not in available_glyph_names for cn in comps):
            continue

        rules.append(f"  sub {' '.join(comps)} by {out};")

    if not rules:
        return ""

    return "feature liga {\n" + "\n".join(rules) + "\n} liga;\n"


# -----------------------------
# Master generation
# -----------------------------
def compute_global_vertical_metrics() -> Tuple[int, int]:
    t_max = hght_scale_from_value(400.0)
    base_y = warp_y_pos(SVG_BASELINE_Y, t_max)
    top_y = warp_y_pos(0.0, t_max)
    bot_y = warp_y_pos(SVG_BASE_H, t_max)

    ascent_svg = base_y - top_y
    descent_svg = bot_y - base_y

    ascent = int(math.ceil(ascent_svg * SCALE))
    descent = -int(math.ceil(descent_svg * SCALE))
    return ascent, descent


def _assert_unique_glyph_order(glyph_order: List[str]) -> None:
    seen: set[str] = set()
    dups: List[str] = []
    for g in glyph_order:
        if g in seen:
            dups.append(g)
        seen.add(g)
    if dups:
        raise RuntimeError(f"Duplicate glyph names in glyph order: {sorted(set(dups))}")


def build_master_ttf(
    *,
    out_path: Path,
    singles: List[SingleGlyph],
    ligatures: List[LigatureDef],
    wdth_value: float,
    hght_value: float,
) -> None:
    s = wdth_scale_from_value(wdth_value)
    t = hght_scale_from_value(hght_value)
    base_y_warped = warp_y_pos(SVG_BASELINE_Y, t)

    single_names = [g.glyph_name for g in singles]
    have_space = "space" in single_names
    lig_names = [l.glyph_name for l in ligatures]

    glyph_order: List[str] = [".notdef"]
    if not have_space:
        glyph_order.append("space")  # fallback space
    glyph_order.extend(single_names)
    glyph_order.extend(lig_names)

    _assert_unique_glyph_order(glyph_order)

    cmap: Dict[int, str] = {g.codepoint: g.glyph_name for g in singles}

    # Optional ĳ mapping if the ligature exists
    lig_ij = next((l for l in ligatures if l.key == "ij"), None)
    if lig_ij and ("i" in single_names) and ("j" in single_names) and 0x0133 not in cmap:
        cmap[0x0133] = lig_ij.glyph_name

    glyf: Dict[str, object] = {".notdef": make_notdef_glyph()}
    hmtx: Dict[str, Tuple[int, int]] = {}

    # Space metrics (from data if available, else fallback)
    if have_space:
        space_entry = next(g for g in singles if g.glyph_name == "space")
        space_adv_svg = space_entry.geom.width_svg + LETTER_SPACE_SVG
    else:
        space_adv_svg = 12.0 + LETTER_SPACE_SVG

    space_adv_font = int(round((space_adv_svg * s) * SCALE))
    if not have_space:
        glyf["space"] = TTGlyphPen(None).glyph()
        hmtx["space"] = (space_adv_font, 0)
    hmtx[".notdef"] = (space_adv_font, 0)

    # Singles from data/glyphs.py
    for sg in singles:
        warped_rings = [
            transform_ring(
                r,
                s=s,
                t=t,
                seam_x=sg.geom.seam_x,
                seam_fix_rows=sg.geom.seam_fix_rows,
                key=sg.geom.key,
            )
            for r in sg.geom.rings
        ]
        glyf[sg.glyph_name] = build_tt_glyph_from_rings(warped_rings, base_y_warped=base_y_warped)

        adv_svg = sg.geom.width_svg + LETTER_SPACE_SVG
        adv_warped = warp_x(
            adv_svg,
            s,
            sg.geom.seam_x,
            seam_fix_rows=sg.geom.seam_fix_rows,
            key=sg.geom.key,
            y=None,
        )
        adv_font = int(round(adv_warped * SCALE))
        hmtx[sg.glyph_name] = (adv_font, 0)

    # Ligatures from SVG (discovered)
    for lig in ligatures:
        gname = lig.glyph_name
        sg = lig.geom

        warped_rings = [
            transform_ring(
                r,
                s=s,
                t=t,
                seam_x=sg.seam_x,
                seam_fix_rows=sg.seam_fix_rows,
                key=sg.key,
            )
            for r in sg.rings
        ]
        glyf[gname] = build_tt_glyph_from_rings(warped_rings, base_y_warped=base_y_warped)

        adv_svg = sg.width_svg + LETTER_SPACE_SVG
        adv_warped = warp_x(
            adv_svg,
            s,
            sg.seam_x,
            seam_fix_rows=sg.seam_fix_rows,
            key=sg.key,
            y=None,
        )
        adv_font = int(round(adv_warped * SCALE))
        hmtx[gname] = (adv_font, 0)

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

    fea = build_fea_liga(ligatures, set(glyph_order))
    if fea.strip():
        addOpenTypeFeaturesFromString(fb.font, fea)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fb.font.save(out_path)


# -----------------------------
# Variable font build
# -----------------------------
def build_variable_font() -> None:
    root = project_root()
    src_dir = root / "src"
    data_py = root / "data" / "glyphs.py"
    out_dir = root / "dist" / "fonts"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy CSS
    write_unst_css(root=root, out_dir=out_dir)

    # Build artifacts
    masters_dir = root / "build" / "fonts" / "_vf_masters"
    masters_dir.mkdir(parents=True, exist_ok=True)

    # Singles now come from data/glyphs.py
    singles = load_single_glyphs_from_data(data_py)
    if not singles:
        raise RuntimeError(f"No single glyphs loaded from {data_py}")

    # Ligatures discovered from src/
    ligatures = load_ligatures_from_src(src_dir)
    if ligatures:
        print(f"Discovered {len(ligatures)} ligatures in {src_dir}:")
        for l in ligatures:
            print(f"  - {l.glyph_name}  <=  {l.svg_path.name}")
    else:
        print(f"[info] No ligature SVGs found in {src_dir} (ligature-u*.svg). Continuing without ligatures.")

    wdths = [25.0, 100.0, 400.0]
    hghts = [25.0, 100.0, 400.0]

    # Clean prior masters/designspace
    for p in masters_dir.glob("unst-master-w*-h*.ttf"):
        try:
            p.unlink()
        except Exception:
            pass
    ds_path = masters_dir / "unst.designspace"
    if ds_path.exists():
        try:
            ds_path.unlink()
        except Exception:
            pass

    master_paths: Dict[Tuple[float, float], Path] = {}
    for w in wdths:
        for h in hghts:
            p = masters_dir / f"unst-master-w{int(w)}-h{int(h)}.ttf"
            build_master_ttf(
                out_path=p,
                singles=singles,
                ligatures=ligatures,
                wdth_value=w,
                hght_value=h,
            )
            master_paths[(w, h)] = p

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
        is_default = (w == 100.0 and h == 100.0)
        src.copyLib = is_default
        src.copyInfo = is_default
        src.copyGroups = is_default
        src.copyFeatures = is_default
        ds.addSource(src)

    ds.write(ds_path)

    vf, _model, _masters = var_build(str(ds_path))

    out_ttf = out_dir / "unst.ttf"
    vf.save(out_ttf)
    print(f"Wrote: {out_ttf}")

    try:
        woff_font = TTFont(out_ttf)
        woff_font.flavor = "woff"
        woff_path = out_dir / "unst.woff"
        woff_font.save(woff_path)
        print(f"Wrote: {woff_path}")
    except Exception as e:
        print(f"Skipping WOFF (error): {e}")

    try:
        woff2_font = TTFont(out_ttf)
        woff2_font.flavor = "woff2"
        woff2_path = out_dir / "unst.woff2"
        woff2_font.save(woff2_path)
        print(f"Wrote: {woff2_path}")
    except Exception as e:
        print(f"Skipping WOFF2 (install 'brotli' to enable) (error): {e}")


if __name__ == "__main__":
    build_variable_font()