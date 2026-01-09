#!/usr/bin/env python3
"""
UNST variable-font sheet (local)

- 1080×1080 PNG, black on white
- Left-aligned
- Fixed font size: 48px
- NO anti-aliasing (monochrome 1-bit rendering in FreeType)
- Wrap to next line when the text doesn't fit
- 4 axis settings rendered as 4 sections, one after the other:
    1) w=100, h=100
    2) w=400, h=25
    3) w=25,  h=400
    4) w=25,  h=25

Tight line spacing:
- line_step computed from actual rendered bitmap extents (not font ascent/descent)
- minimal SECTION_GAP_PX between the 4 sections

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

SPECIAL_GLYPHS = ["st", "es", "yp"]

MARGIN_X = 24
MARGIN_Y = 24

FONT_PX = 48 * 2

# Tight spacing controls
EXTRA_LEADING_PX = 0     # extra pixels between lines (0..2)
SECTION_GAP_PX = 240       # pixels between the 4 axis sections

# FreeType flags for NO anti-aliasing:
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
    """
    Convert FreeType bitmap to an 'L' mask (0..255).

    Handles MONO (1-bit packed) and GRAY (fallback).
    """
    w, h = bmp.width, bmp.rows
    if w <= 0 or h <= 0:
        return Image.new("L", (1, 1), 0)

    buf = bmp.buffer
    if isinstance(buf, memoryview):
        buf = buf.tobytes()
    else:
        buf = bytes(buf)

    pitch = bmp.pitch
    flip = False
    if pitch < 0:
        pitch = -pitch
        flip = True

    # MONOCHROME: bits packed, 8 pixels per byte
    if getattr(bmp, "pixel_mode", None) == freetype.FT_PIXEL_MODE_MONO:
        out = Image.new("L", (w, h), 0)
        for y in range(h):
            row = buf[y * pitch : (y + 1) * pitch]
            for x in range(w):
                byte = row[x >> 3]
                bit = 7 - (x & 7)
                on = (byte >> bit) & 1
                out.putpixel((x, y), 255 if on else 0)
        if flip:
            out = out.transpose(Image.FLIP_TOP_BOTTOM)
        return out

    # GRAY fallback
    if pitch == 0 or pitch == w:
        im = Image.frombytes("L", (w, h), buf)
    else:
        im = Image.frombytes("L", (w, h), buf, "raw", "L", pitch, 0)

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


Token = Tuple[str, Optional[str]]  # ("char","A") | ("glyph","st") | ("gap",None)


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

    glyph_order = set(base_tt.getGlyphOrder())
    ligs = [g for g in SPECIAL_GLYPHS if g in glyph_order]

    tokens: List[Token] = [("char", ch) for ch in chars]

    # Only spacing between ligatures (implemented as a pixel gap):
    if ligs:
        tokens.append(("gap", None))  # separator before first ligature
        for i, g in enumerate(ligs):
            tokens.append(("glyph", g))
            if i != len(ligs) - 1:
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


def space_advance_px(face: freetype.Face, font_px: int) -> float:
    try:
        face.load_char(" ", freetype.FT_LOAD_DEFAULT)
        adv = face.glyph.advance.x / 64.0
        if adv > 0:
            return float(adv)
    except Exception:
        pass
    return max(6.0, font_px * 0.33)


def compute_tight_line_metrics(
    face: freetype.Face,
    tokens: List[Token],
    gmap: Dict[str, int],
    font_px: int,
) -> Tuple[int, int, int]:
    """
    Compute (above, below, line_step) in pixels from rendered bitmaps:
      above = max(bitmap_top)
      below = max(bitmap_rows - bitmap_top)
      line_step = above + below + EXTRA_LEADING_PX

    This ignores font ascender/descender/lineGap so spacing is truly tight.
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
        bh = g.bitmap.rows
        bt = g.bitmap_top

        # Only consider glyphs that actually render pixels
        if g.bitmap.width > 0 and bh > 0:
            if bt > above:
                above = bt
            b = bh - bt
            if b > below:
                below = b

    if above == 0 and below == 0:
        # fallback
        above = int(round(font_px * 0.8))
        below = int(round(font_px * 0.2))

    line_step = above + below + int(EXTRA_LEADING_PX)
    return int(above), int(below), int(line_step)


def render_section(
    canvas: Image.Image,
    inst_path: Path,
    tokens: List[Token],
    y_cursor: int,
    font_px: int,
) -> int:
    avail_w = CANVAS_W - 2 * MARGIN_X

    face = freetype.Face(str(inst_path))
    face.set_pixel_sizes(0, font_px)

    tt = TTFont(str(inst_path))
    order = tt.getGlyphOrder()
    gmap = {name: i for i, name in enumerate(order)}

    gap_px = space_advance_px(face, font_px)

    above, below, line_step = compute_tight_line_metrics(face, tokens, gmap, font_px)
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

    # If we're already too low, bail
    if (y_cursor + line_step) > (CANVAS_H - MARGIN_Y):
        return CANVAS_H

    for kind, val in tokens:
        if kind == "gap":
            if pen_x == 0.0:
                continue
            adv = gap_px
            if pen_x > 0.0 and (pen_x + adv) > avail_w:
                if not new_line():
                    break
                continue
            pen_x += adv
            continue

        # Load + render glyph (MONO => no AA)
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
        bw, bh = bmp.width, bmp.rows
        if bw > 0 and bh > 0:
            mask = ft_bitmap_to_mask(bmp)
            x = MARGIN_X + pen_x + g.bitmap_left
            y = baseline_y - g.bitmap_top
            paste_mask_clipped(canvas, mask, int(round(x)), int(round(y)))

        pen_x += adv

        if (y_cursor + line_step) > (CANVAS_H - MARGIN_Y):
            break

    # Small gap between sections
    y_cursor += int(SECTION_GAP_PX)
    return y_cursor


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    default_font = (script_dir / "../dist/fonts/unst-variable.ttf").resolve()

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--font",
        type=Path,
        default=default_font,
        help="Path to variable TTF (default: ../dist/fonts/unst-variable.ttf relative to this script)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PNG (default: ./unst-characters-1080-<timestamp>.png)",
    )
    args = ap.parse_args()

    font_path: Path = args.font
    if not font_path.exists():
        raise SystemExit(f"Font not found: {font_path}")

    base_tt = TTFont(str(font_path))
    if "fvar" not in base_tt:
        raise SystemExit("Font is not variable (missing fvar table).")

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
    print(f"font_px: {FONT_PX} (monochrome, no anti-aliasing)")
    print(f"EXTRA_LEADING_PX={EXTRA_LEADING_PX}, SECTION_GAP_PX={SECTION_GAP_PX}")
    print("Sections:", ", ".join([f"w={int(w)} h={int(h)}" for (w, h) in AXIS_SETTINGS]))


if __name__ == "__main__":
    main()
