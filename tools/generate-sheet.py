#!/usr/bin/env python3
"""
UNST variable-font sheet (local)

- 1080×1080 PNG, black on white
- Left-aligned
- Fixed font size: 64px
- NO anti-aliasing (FreeType MONO 1-bit)
- Wrap to next line when it doesn't fit
- 4 axis settings rendered as 4 sections, one after the other:
    1) w=100, h=100
    2) w=400, h=25
    3) w=25,  h=400
    4) w=25,  h=25

Ligatures appended at the end (if present as glyph names):
["st", "ch", "ct", "fi", "ij", "sh", "es", "yp"]
with TWO normal spaces between ligatures.

Spacing:
- 1 px between lines
- 1 px between sections (in addition to moving to the next line)

Deps:
  pip install freetype-py pillow fonttools
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import freetype
from PIL import Image
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

CANVAS_W, CANVAS_H = 1080, 1080

AXIS_SETTINGS: List[Tuple[float, float]] = [
    (100.0, 100.0),
    (400.0, 25.0),
    (25.0,  400.0),
    (25.0,  25.0),
]

WDTH_MIN, WDTH_MAX = 25.0, 400.0
HGHT_MIN, HGHT_MAX = 25.0, 400.0

LIGATURES = ["st", "ch", "ct", "fi", "ij", "sh", "es", "yp"]

MARGIN_X = 24
MARGIN_Y = 24

FONT_PX = 64

# EXACTLY what you asked for:
LINE_GAP_PX = 1       # space between lines
SECTION_GAP_PX = 1    # extra space between sections (after moving to next line)

# TWO normal spaces between ligatures
LIGATURE_SPACE_COUNT = 2

# 1-bit monochrome rendering (no AA)
FT_FLAGS_MONO = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO | freetype.FT_LOAD_MONOCHROME


def clamp(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def char_sort_key(ch: str) -> Tuple[int, int]:
    o = ord(ch)
    if "0" <= ch <= "9":
        grp = 0
    elif "A" <= ch <= "Z":
        grp = 1
    elif "a" <= ch <= "z":
        grp = 2
    else:
        grp = 3
    return (grp, o)


def ft_bitmap_to_mask(bmp: freetype.Bitmap) -> Image.Image:
    """Convert FreeType bitmap -> PIL 'L' mask (supports MONO packed bits)."""
    w, h = bmp.width, bmp.rows
    if w <= 0 or h <= 0:
        return Image.new("L", (1, 1), 0)

    buf = bmp.buffer.tobytes() if isinstance(bmp.buffer, memoryview) else bytes(bmp.buffer)

    pitch = bmp.pitch
    flip = False
    if pitch < 0:
        pitch = -pitch
        flip = True

    if getattr(bmp, "pixel_mode", None) == freetype.FT_PIXEL_MODE_MONO:
        out = Image.new("L", (w, h), 0)
        for y in range(h):
            row = buf[y * pitch : (y + 1) * pitch]
            for x in range(w):
                byte = row[x >> 3]
                bit = 7 - (x & 7)
                out.putpixel((x, y), 255 if ((byte >> bit) & 1) else 0)
        if flip:
            out = out.transpose(Image.FLIP_TOP_BOTTOM)
        return out

    # fallback (shouldn't happen with MONO flags, but keep robust)
    im = Image.frombytes("L", (w, h), buf, "raw", "L", pitch, 0) if pitch not in (0, w) else Image.frombytes("L", (w, h), buf)
    if flip:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
    return im


def paste_mask_clipped(dst: Image.Image, mask: Image.Image, x: int, y: int) -> None:
    bw, bh = mask.size
    x0, y0 = x, y
    x1, y1 = x + bw, y + bh

    ix0 = max(0, x0)
    iy0 = max(0, y0)
    ix1 = min(dst.size[0], x1)
    iy1 = min(dst.size[1], y1)
    if ix0 >= ix1 or iy0 >= iy1:
        return

    mx0 = ix0 - x0
    my0 = iy0 - y0
    mx1 = mx0 + (ix1 - ix0)
    my1 = my0 + (iy1 - iy0)

    m = mask.crop((mx0, my0, mx1, my1))
    dst.paste(0, (ix0, iy0, ix1, iy1), m)


Token = Tuple[str, Optional[str]]  # ("char","a") | ("glyph","st") | ("gap",None)


def build_tokens(base_tt: TTFont) -> List[Token]:
    best_cmap: Dict[int, str] = base_tt["cmap"].getBestCmap() or {}
    chars: List[str] = []
    for cp in sorted(best_cmap.keys()):
        if cp < 32:
            continue
        ch = chr(cp)
        if ch.isspace():
            continue
        chars.append(ch)

    chars = sorted(set(chars), key=char_sort_key)
    tokens: List[Token] = [("char", ch) for ch in chars]

    # append ligatures by glyph name if present
    glyph_order = set(base_tt.getGlyphOrder())
    ligs_present = [g for g in LIGATURES if g in glyph_order]

    if ligs_present:
        # keep a little separation before the ligature run (two spaces, as requested style)
        for _ in range(LIGATURE_SPACE_COUNT):
            tokens.append(("gap", None))

        for i, g in enumerate(ligs_present):
            tokens.append(("glyph", g))
            if i != len(ligs_present) - 1:
                for _ in range(LIGATURE_SPACE_COUNT):
                    tokens.append(("gap", None))

    return tokens


def make_instance(font_path: Path, tmpdir: Path, wdth: float, hght: float) -> Path:
    wd = clamp(wdth, WDTH_MIN, WDTH_MAX)
    hg = clamp(hght, HGHT_MIN, HGHT_MAX)
    out_path = tmpdir / f"unst_w{wd:g}_h{hg:g}.ttf"
    tt = TTFont(str(font_path))
    inst_tt = instancer.instantiateVariableFont(tt, {"wdth": wd, "hght": hg}, inplace=False)
    inst_tt.save(str(out_path))
    return out_path


def normal_space_advance_px(face: freetype.Face, font_px: int) -> float:
    """
    Use the font's real space advance, BUT clamp it to a sane range so a broken
    space width can't explode spacing.
    """
    adv = None
    try:
        face.load_char(" ", freetype.FT_LOAD_DEFAULT)
        a = face.glyph.advance.x / 64.0
        if a > 0:
            adv = float(a)
    except Exception:
        adv = None

    if adv is None:
        adv = 0.5 * font_px  # reasonable fallback

    # Clamp: prevents huge gaps while still behaving like "normal space"
    lo = 0.20 * font_px
    hi = 0.75 * font_px
    return float(max(lo, min(hi, adv)))


def compute_tight_line_metrics(face: freetype.Face, tokens: List[Token], gmap: Dict[str, int]) -> Tuple[int, int, int]:
    """
    Compute line step from *actual rendered bitmap extents*:
      above = max(bitmap_top)
      below = max(bitmap_rows - bitmap_top)
      line_step = above + below + LINE_GAP_PX
    """
    above = 0
    below = 0

    for kind, val in tokens:
        if kind == "gap":
            continue
        try:
            if kind == "char":
                face.load_char(val or "", FT_FLAGS_MONO)
            else:
                gid = gmap.get(val or "")
                if gid is None:
                    continue
                face.load_glyph(gid, FT_FLAGS_MONO)
        except Exception:
            continue

        g = face.glyph
        if g.bitmap.width <= 0 or g.bitmap.rows <= 0:
            continue

        above = max(above, int(g.bitmap_top))
        below = max(below, int(g.bitmap.rows - g.bitmap_top))

    if above == 0 and below == 0:
        above = int(round(0.8 * FONT_PX))
        below = int(round(0.2 * FONT_PX))

    line_step = above + below + int(LINE_GAP_PX)
    return int(above), int(below), int(line_step)


def render_section(canvas: Image.Image, inst_path: Path, tokens: List[Token], y_cursor: int, font_px: int) -> int:
    avail_w = CANVAS_W - 2 * MARGIN_X

    face = freetype.Face(str(inst_path))
    face.set_pixel_sizes(0, font_px)

    tt = TTFont(str(inst_path))
    order = tt.getGlyphOrder()
    gmap = {name: i for i, name in enumerate(order)}

    space_px = normal_space_advance_px(face, font_px)
    above, below, line_step = compute_tight_line_metrics(face, tokens, gmap)

    baseline_y = y_cursor + above
    pen_x = 0.0

    def new_line() -> bool:
        nonlocal y_cursor, baseline_y, pen_x
        y_cursor += line_step
        if (y_cursor + line_step) > (CANVAS_H - MARGIN_Y):
            return False
        baseline_y = y_cursor + above
        pen_x = 0.0
        return True

    if (y_cursor + line_step) > (CANVAS_H - MARGIN_Y):
        return CANVAS_H

    for kind, val in tokens:
        if kind == "gap":
            if pen_x == 0.0:
                continue
            adv = space_px
            if pen_x > 0.0 and (pen_x + adv) > avail_w:
                if not new_line():
                    break
                continue
            pen_x += adv
            continue

        # render glyph
        try:
            if kind == "char":
                face.load_char(val or "", FT_FLAGS_MONO)
            else:
                gid = gmap.get(val or "")
                if gid is None:
                    continue
                face.load_glyph(gid, FT_FLAGS_MONO)
        except Exception:
            continue

        g = face.glyph
        adv = g.advance.x / 64.0

        if pen_x > 0.0 and (pen_x + adv) > avail_w:
            if not new_line():
                break

        bmp = g.bitmap
        if bmp.width > 0 and bmp.rows > 0:
            mask = ft_bitmap_to_mask(bmp)
            x = MARGIN_X + pen_x + g.bitmap_left
            y = baseline_y - g.bitmap_top
            paste_mask_clipped(canvas, mask, int(round(x)), int(round(y)))

        pen_x += adv

        if (y_cursor + line_step) > (CANVAS_H - MARGIN_Y):
            break

    # Move to the next line, then add the requested 1px section gap
    y_cursor += line_step + int(SECTION_GAP_PX)
    return y_cursor


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    default_font = (script_dir / "../dist/fonts/unst-variable.ttf").resolve()

    ap = argparse.ArgumentParser()
    ap.add_argument("--font", type=Path, default=default_font)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    font_path: Path = args.font
    if not font_path.exists():
        raise SystemExit(f"Font not found: {font_path}")

    base_tt = TTFont(str(font_path))
    if "fvar" not in base_tt:
        raise SystemExit("Font is not variable (missing fvar).")

    axis_tags = [a.axisTag for a in base_tt["fvar"].axes]
    if "wdth" not in axis_tags or "hght" not in axis_tags:
        raise SystemExit(f"Expected axes wdth + hght. Found: {axis_tags}")

    tokens = build_tokens(base_tt)
    if not tokens:
        raise SystemExit("No renderable characters found in cmap.")

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_path = args.out or Path(f"unst-characters-1080-{ts}.png")

    canvas = Image.new("L", (CANVAS_W, CANVAS_H), 255)

    with tempfile.TemporaryDirectory(prefix="unst_chars_") as td:
        tmpdir = Path(td)
        inst_paths = [make_instance(font_path, tmpdir, w, h) for (w, h) in AXIS_SETTINGS]

        y = int(MARGIN_Y)
        for ip in inst_paths:
            y = render_section(canvas, ip, tokens, y, FONT_PX)
            if y >= CANVAS_H - MARGIN_Y:
                break

    canvas.convert("RGB").save(str(out_path))
    print(f"Wrote: {out_path.resolve()}")
    print(f"font_px: {FONT_PX} (MONO, no AA)")
    print(f"LINE_GAP_PX={LINE_GAP_PX}, SECTION_GAP_PX={SECTION_GAP_PX}")
    print("Sections:", ", ".join([f"w={int(w)} h={int(h)}" for (w, h) in AXIS_SETTINGS]))


if __name__ == "__main__":
    main()
