#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/generate-video.py

Generate an animated video from a variable font using text from:
    config/video-text.txt

Outputs:
    dist/videos/{sanitized_text}-{timestamp}.{ext}

Features:
- Runs locally (no notebook / Colab required)
- Shapes normal Unicode text with HarfBuzz
- Supports multiple lines
- Optional image fill for text and/or background
- Image fill behaves like CSS:
      background-size: cover;
      background-position: center center;
  with optional position overrides

Examples:
    python tools/generate-video.py --font dist/fonts/unst.ttf

    python tools/generate-video.py \
        --font dist/fonts/unst.ttf \
        --text-image "https://example.com/texture.jpg" \
        --bg-image "images/background.jpg"

    python tools/generate-video.py \
        --font dist/fonts/unst.ttf \
        --text-image "images/portrait.jpg" \
        --text-image-position "left center" \
        --bg-image "images/bg.jpg" \
        --bg-image-position "50% 20%"
"""

from __future__ import annotations

import argparse
import atexit
import math
import re
import shutil
import tempfile
import unicodedata
from collections import OrderedDict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import freetype
import imageio.v2 as imageio
import numpy as np
import uharfbuzz as hb
from PIL import Image, ImageOps
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from tqdm import tqdm


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

DEFAULT_TEXT_PATH = ROOT / "config" / "video-text.txt"
DEFAULT_OUT_DIR = ROOT / "dist" / "videos"
INSTANCE_DIR = Path(tempfile.gettempdir()) / "unst-video-instances"


# ------------------------------------------------------------
# Defaults
# ------------------------------------------------------------

DEFAULT_W = 1080
DEFAULT_H = 1080
DEFAULT_FPS = 30
DEFAULT_FONT_PX = 128
DEFAULT_LINE_HEIGHT = 1.20

DEFAULT_HOLD_S = 1.00
DEFAULT_MOVE_S = 2.00

DEFAULT_ROUND_TO = 1.0
DEFAULT_CACHE_MAX = 64

DEFAULT_STATES: List[Tuple[float, float]] = [
    (100.0, 100.0),
    (400.0, 100.0),
    (400.0, 400.0),
    (25.0,  400.0),
    (25.0,  25.0),
    (100.0, 25.0),
    (100.0, 100.0),
]


# ------------------------------------------------------------
# Temp cleanup
# ------------------------------------------------------------

INSTANCE_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_instance_dir() -> None:
    try:
        shutil.rmtree(INSTANCE_DIR, ignore_errors=True)
    except Exception:
        pass


atexit.register(_cleanup_instance_dir)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def ease_in_out_sine(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ft_bitmap_to_mask(bmp: freetype.Bitmap) -> Image.Image:
    w, h = bmp.width, bmp.rows
    if w <= 0 or h <= 0:
        return Image.new("L", (1, 1), 0)

    buf = bmp.buffer
    if isinstance(buf, memoryview):
        buf = buf.tobytes()
    elif isinstance(buf, (list, tuple)):
        buf = bytes(buf)
    else:
        buf = bytes(buf)

    pitch = bmp.pitch
    flip = False
    if pitch < 0:
        pitch = -pitch
        flip = True

    if pitch == 0 or pitch == w:
        im = Image.frombytes("L", (w, h), buf)
    else:
        im = Image.frombytes("L", (w, h), buf, "raw", "L", pitch, 0)

    if flip:
        im = im.transpose(Image.FLIP_TOP_BOTTOM)

    return im


def paste_mask_clipped(dst: Image.Image, mask: Image.Image, x: int, y: int, W: int, H: int, fill: int = 255) -> None:
    bw, bh = mask.size
    x0, y0 = x, y
    x1, y1 = x + bw, y + bh

    ix0 = max(0, x0)
    iy0 = max(0, y0)
    ix1 = min(W, x1)
    iy1 = min(H, y1)
    if ix0 >= ix1 or iy0 >= iy1:
        return

    mx0 = ix0 - x0
    my0 = iy0 - y0
    mx1 = mx0 + (ix1 - ix0)
    my1 = my0 + (iy1 - iy0)

    m = mask.crop((mx0, my0, mx1, my1))
    dst.paste(fill, (ix0, iy0, ix1, iy1), m)


def slugify_text(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip().lower()
    if not text:
        return "video"

    text = re.sub(r"\s+", "-", text, flags=re.UNICODE)
    text = re.sub(r"[^\w\-]+", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text, flags=re.UNICODE)
    text = text.strip("-_")
    if not text:
        return "video"

    return text[:max_len].rstrip("-_") or "video"


def read_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Text file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def validate_variable_font(font_path: Path) -> Dict[str, Tuple[float, float, float]]:
    tt = TTFont(str(font_path))
    try:
        if "fvar" not in tt:
            raise RuntimeError(f"Not a variable font: {font_path}")

        axes = {}
        for axis in tt["fvar"].axes:
            axes[axis.axisTag] = (
                float(axis.minValue),
                float(axis.defaultValue),
                float(axis.maxValue),
            )
        return axes
    finally:
        tt.close()


def font_has_required_axes(font_path: Path, required: Sequence[str] = ("wdth", "hght")) -> bool:
    try:
        axes = validate_variable_font(font_path)
        return all(tag in axes for tag in required)
    except Exception:
        return False


def find_default_font() -> Path:
    preferred = [
        ROOT / "dist" / "fonts" / "unst.ttf",
        ROOT / "dist" / "fonts" / "UNST.ttf",
        ROOT / "dist" / "fonts" / "unst-variable.ttf",
        ROOT / "dist" / "fonts" / "UNST-variable.ttf",
        ROOT / "dist" / "fonts" / "unst.otf",
        ROOT / "dist" / "fonts" / "UNST.otf",
    ]

    for path in preferred:
        if path.exists() and font_has_required_axes(path):
            return path

    font_dir = ROOT / "dist" / "fonts"
    for pattern in ("*.ttf", "*.otf"):
        for path in sorted(font_dir.glob(pattern)):
            if font_has_required_axes(path):
                return path

    raise FileNotFoundError(
        "Could not find a variable font with wdth+hght in dist/fonts. "
        "Pass one explicitly with --font."
    )


def build_axis_sequence(
    states: Sequence[Tuple[float, float]],
    fps: int,
    hold_s: float,
    move_s: float,
    wdth_min: float,
    wdth_max: float,
    hght_min: float,
    hght_max: float,
) -> Tuple[np.ndarray, np.ndarray]:
    hold_fr = int(round(hold_s * fps))
    move_fr = int(round(move_s * fps))

    wd_seq: List[float] = []
    hg_seq: List[float] = []

    def append_hold(w: float, h: float) -> None:
        wd_seq.extend([w] * hold_fr)
        hg_seq.extend([h] * hold_fr)

    def append_move(w0: float, h0: float, w1: float, h1: float) -> None:
        ts = np.linspace(0.0, 1.0, move_fr + 1, endpoint=True)[1:]
        for t in ts:
            tt = ease_in_out_sine(float(t))
            wd_seq.append(lerp(w0, w1, tt))
            hg_seq.append(lerp(h0, h1, tt))

    w0, h0 = states[0]
    append_hold(w0, h0)
    for w1, h1 in states[1:]:
        append_move(w0, h0, w1, h1)
        append_hold(w1, h1)
        w0, h0 = w1, h1

    wdth_vals = np.clip(np.array(wd_seq, dtype=np.float64), wdth_min, wdth_max)
    hght_vals = np.clip(np.array(hg_seq, dtype=np.float64), hght_min, hght_max)
    return wdth_vals, hght_vals


# ------------------------------------------------------------
# Image source / cover-fill helpers
# ------------------------------------------------------------

def is_url(value: str) -> bool:
    scheme = urlparse(value).scheme.lower()
    return scheme in {"http", "https"}


def load_image_source(source: str) -> Image.Image:
    """
    Load a raster image from a local path or URL.

    Note:
    - This uses Pillow, so supported formats depend on Pillow plugins.
    - Typical PNG/JPEG/WebP/TIFF/BMP are fine.
    """
    if is_url(source):
        req = Request(
            source,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; generate-video.py)"
            },
        )
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
        im = Image.open(BytesIO(data))
    else:
        path = Path(source).expanduser()
        if not path.is_absolute():
            path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        im = Image.open(path)

    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def _parse_position_token(token: str, axis: str) -> float:
    token = token.strip().lower()

    if axis == "x":
        kw = {"left": 0.0, "center": 0.5, "right": 1.0}
    else:
        kw = {"top": 0.0, "center": 0.5, "bottom": 1.0}

    if token in kw:
        return kw[token]

    if token.endswith("%"):
        try:
            return max(0.0, min(1.0, float(token[:-1]) / 100.0))
        except ValueError:
            pass

    try:
        value = float(token)
        if 0.0 <= value <= 1.0:
            return value
        if 0.0 <= value <= 100.0:
            return value / 100.0
    except ValueError:
        pass

    raise ValueError(f"Invalid {axis}-position token: {token!r}")


def parse_position(value: str | None) -> Tuple[float, float]:
    """
    Parses a CSS-ish background-position style value.

    Supported examples:
      "center center"
      "left top"
      "right center"
      "50% 20%"
      "0.5 0.2"
      "left"
      "top"
      "75%"

    Default is center center.
    """
    if value is None:
        return 0.5, 0.5

    parts = [p for p in re.split(r"[\s,]+", value.strip()) if p]
    if not parts:
        return 0.5, 0.5

    horizontal = {"left", "center", "right"}
    vertical = {"top", "center", "bottom"}

    if len(parts) == 1:
        p = parts[0].lower()
        if p in {"top", "bottom"}:
            return 0.5, _parse_position_token(p, "y")
        return _parse_position_token(p, "x"), 0.5

    a = parts[0].lower()
    b = parts[1].lower()

    # Allow "top left" / "left top"
    if a in vertical and b in horizontal:
        return _parse_position_token(b, "x"), _parse_position_token(a, "y")
    if a in horizontal and b in vertical:
        return _parse_position_token(a, "x"), _parse_position_token(b, "y")

    # Otherwise: first = x, second = y
    return _parse_position_token(parts[0], "x"), _parse_position_token(parts[1], "y")


def cover_resize_and_crop(
    im: Image.Image,
    out_w: int,
    out_h: int,
    pos_x: float = 0.5,
    pos_y: float = 0.5,
) -> Image.Image:
    src_w, src_h = im.size
    if src_w <= 0 or src_h <= 0:
        raise ValueError("Source image has invalid size.")

    scale = max(out_w / src_w, out_h / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))

    resized = im.resize((new_w, new_h), Image.LANCZOS)

    extra_x = max(0, new_w - out_w)
    extra_y = max(0, new_h - out_h)

    left = int(round(extra_x * max(0.0, min(1.0, pos_x))))
    top = int(round(extra_y * max(0.0, min(1.0, pos_y))))

    left = max(0, min(left, extra_x))
    top = max(0, min(top, extra_y))

    return resized.crop((left, top, left + out_w, top + out_h)).convert("RGB")


def make_cover_layer(
    source: str | None,
    out_w: int,
    out_h: int,
    position: str | None,
    fallback_rgb: Tuple[int, int, int],
) -> Image.Image:
    if not source:
        return Image.new("RGB", (out_w, out_h), fallback_rgb)

    pos_x, pos_y = parse_position(position)
    im = load_image_source(source)
    return cover_resize_and_crop(im, out_w, out_h, pos_x=pos_x, pos_y=pos_y)


# ------------------------------------------------------------
# Font instancing / shaping caches
# ------------------------------------------------------------

_instance_cache: "OrderedDict[Tuple[float, float], Path]" = OrderedDict()
_hb_cache: Dict[str, Tuple[hb.Font, int]] = {}


def quantize(value: float, step: float) -> float:
    return float(round(value / step) * step) if step > 0 else float(value)


def instance_font_path(
    base_font_path: Path,
    wdth: float,
    hght: float,
    wdth_min: float,
    wdth_max: float,
    hght_min: float,
    hght_max: float,
    round_to: float,
    cache_max: int,
) -> Path:
    wd = quantize(float(np.clip(wdth, wdth_min, wdth_max)), round_to)
    hg = quantize(float(np.clip(hght, hght_min, hght_max)), round_to)
    key = (wd, hg)

    if key in _instance_cache:
        _instance_cache.move_to_end(key)
        return _instance_cache[key]

    out_path = INSTANCE_DIR / f"{base_font_path.stem}-w{wd:g}-h{hg:g}.ttf"

    tt = TTFont(str(base_font_path))
    try:
        inst_tt = instancer.instantiateVariableFont(
            tt,
            {"wdth": wd, "hght": hg},
            inplace=False,
        )
        inst_tt.save(str(out_path))
    finally:
        try:
            tt.close()
        except Exception:
            pass

    _instance_cache[key] = out_path
    _instance_cache.move_to_end(key)

    while len(_instance_cache) > cache_max:
        _, old_path = _instance_cache.popitem(last=False)
        try:
            old_path.unlink(missing_ok=True)
        except Exception:
            pass

    return out_path


def hb_font_for_instance(inst_path: Path) -> Tuple[hb.Font, int]:
    key = str(inst_path)
    cached = _hb_cache.get(key)
    if cached is not None:
        return cached

    data = inst_path.read_bytes()
    face = hb.Face(data)
    font = hb.Font(face)
    hb.ot_font_set_funcs(font)

    upm = int(face.upem)
    font.scale = (upm, upm)

    _hb_cache[key] = (font, upm)
    return font, upm


def shape_line(text: str, hb_font: hb.Font, upm: int, font_px: int) -> List[Tuple[int, float, float]]:
    if not text:
        return []

    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)

    scale = float(font_px) / float(upm)
    out: List[Tuple[int, float, float]] = []

    pen_x = 0.0
    pen_y = 0.0

    infos = buf.glyph_infos
    positions = buf.glyph_positions

    for info, pos in zip(infos, positions):
        x = pen_x + (pos.x_offset * scale)
        y = pen_y + (pos.y_offset * scale)
        out.append((int(info.codepoint), float(x), float(y)))

        pen_x += pos.x_advance * scale
        pen_y += pos.y_advance * scale

    return out


# ------------------------------------------------------------
# Rendering
# ------------------------------------------------------------

def render_text_mask_centered(
    inst_path: Path,
    text: str,
    font_px: int,
    W: int,
    H: int,
    line_height: float,
) -> Image.Image:
    """
    Returns an L-mode mask:
      black   = outside text
      white   = text ink
    """
    lines = text.expandtabs(4).split("\n")
    if not lines:
        lines = [""]

    face = freetype.Face(str(inst_path))
    face.set_pixel_sizes(0, font_px)

    hb_font, upm = hb_font_for_instance(inst_path)

    per_line_runs = []
    line_advance = font_px * line_height

    for line in lines:
        shaped = shape_line(line, hb_font, upm, font_px)

        run = []
        x_min, y_min = float("inf"), float("inf")
        x_max, y_max = float("-inf"), float("-inf")

        for gid, x_off, y_off in shaped:
            face.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
            g = face.glyph
            bmp = g.bitmap
            bw, bh = bmp.width, bmp.rows

            left = x_off + g.bitmap_left
            top = -y_off - g.bitmap_top

            mask = ft_bitmap_to_mask(bmp)
            run.append((mask, left, top))

            if bw > 0 and bh > 0:
                x0 = left
                y0 = top
                x1 = left + bw
                y1 = y0 + bh
                x_min = min(x_min, x0)
                y_min = min(y_min, y0)
                x_max = max(x_max, x1)
                y_max = max(y_max, y1)

        if x_max >= x_min and y_max >= y_min:
            line_center_shift_x = -((x_min + x_max) / 2.0)
        else:
            line_center_shift_x = 0.0

        per_line_runs.append((run, line_center_shift_x))

    g_x_min, g_y_min = float("inf"), float("inf")
    g_x_max, g_y_max = float("-inf"), float("-inf")

    for line_idx, (run, line_shift_x) in enumerate(per_line_runs):
        baseline_y = line_idx * line_advance
        for mask, left, top in run:
            bw, bh = mask.size
            if bw <= 0 or bh <= 0:
                continue

            x0 = left + line_shift_x
            y0 = top + baseline_y
            x1 = x0 + bw
            y1 = y0 + bh

            g_x_min = min(g_x_min, x0)
            g_y_min = min(g_y_min, y0)
            g_x_max = max(g_x_max, x1)
            g_y_max = max(g_y_max, y1)

    img = Image.new("L", (W, H), 0)

    if not (g_x_max >= g_x_min and g_y_max >= g_y_min):
        return img

    shift_x = (W / 2.0) - ((g_x_min + g_x_max) / 2.0)
    shift_y = (H / 2.0) - ((g_y_min + g_y_max) / 2.0)

    for line_idx, (run, line_shift_x) in enumerate(per_line_runs):
        baseline_y = line_idx * line_advance
        for mask, left, top in run:
            xi = int(round(left + line_shift_x + shift_x))
            yi = int(round(top + baseline_y + shift_y))
            if mask.size[0] > 0 and mask.size[1] > 0:
                paste_mask_clipped(img, mask, xi, yi, W, H, fill=255)

    return img


def composite_frame(
    text_mask: Image.Image,
    bg_layer: Image.Image,
    text_layer: Image.Image,
) -> Image.Image:
    """
    Uses text_mask to take pixels from text_layer where the text is,
    otherwise from bg_layer.
    """
    return Image.composite(text_layer, bg_layer, text_mask).convert("RGB")


# ------------------------------------------------------------
# Writer
# ------------------------------------------------------------

def make_writer(out_path: Path, fps: int):
    ext = out_path.suffix.lower().lstrip(".")
    if ext in {"mp4", "m4v", "mov"}:
        return imageio.get_writer(
            str(out_path),
            fps=fps,
            codec="libx264",
            quality=8,
            pixelformat="yuv420p",
        )
    if ext == "webm":
        return imageio.get_writer(
            str(out_path),
            fps=fps,
            codec="libvpx-vp9",
            pixelformat="yuv420p",
        )
    if ext == "gif":
        return imageio.get_writer(
            str(out_path),
            mode="I",
            fps=fps,
            loop=0,
        )
    raise ValueError(f"Unsupported extension: .{ext}")


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a variable-font animation video from config/video-text.txt")
    p.add_argument("--font", type=Path, default=None, help="Path to a variable TTF/OTF font. Default: auto-detect in dist/fonts.")
    p.add_argument("--text", type=Path, default=DEFAULT_TEXT_PATH, help=f"Text file to render. Default: {DEFAULT_TEXT_PATH}")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help=f"Output directory. Default: {DEFAULT_OUT_DIR}")
    p.add_argument("--ext", type=str, default="mp4", help="Output extension: mp4, mov, m4v, webm, gif. Default: mp4")

    p.add_argument("--width", type=int, default=DEFAULT_W, help=f"Canvas width. Default: {DEFAULT_W}")
    p.add_argument("--height", type=int, default=DEFAULT_H, help=f"Canvas height. Default: {DEFAULT_H}")
    p.add_argument("--fps", type=int, default=DEFAULT_FPS, help=f"Frames per second. Default: {DEFAULT_FPS}")
    p.add_argument("--font-px", type=int, default=DEFAULT_FONT_PX, help=f"Font size in pixels. Default: {DEFAULT_FONT_PX}")
    p.add_argument("--line-height", type=float, default=DEFAULT_LINE_HEIGHT, help=f"Line height multiplier. Default: {DEFAULT_LINE_HEIGHT}")

    p.add_argument("--hold", type=float, default=DEFAULT_HOLD_S, help=f"Hold duration per state, seconds. Default: {DEFAULT_HOLD_S}")
    p.add_argument("--move", type=float, default=DEFAULT_MOVE_S, help=f"Move duration between states, seconds. Default: {DEFAULT_MOVE_S}")

    p.add_argument("--wdth-min", type=float, default=None, help="Override wdth axis minimum.")
    p.add_argument("--wdth-max", type=float, default=None, help="Override wdth axis maximum.")
    p.add_argument("--hght-min", type=float, default=None, help="Override hght axis minimum.")
    p.add_argument("--hght-max", type=float, default=None, help="Override hght axis maximum.")

    p.add_argument("--round-to", type=float, default=DEFAULT_ROUND_TO, help=f"Axis rounding step for instance cache. Default: {DEFAULT_ROUND_TO}")
    p.add_argument("--cache-max", type=int, default=DEFAULT_CACHE_MAX, help=f"Max cached instances. Default: {DEFAULT_CACHE_MAX}")

    p.add_argument("--text-image", type=str, default=None, help="URL or local file path for text fill image.")
    p.add_argument("--bg-image", type=str, default=None, help="URL or local file path for background fill image.")
    p.add_argument("--text-image-position", type=str, default="center center", help='CSS-ish position for text image cover crop. Default: "center center"')
    p.add_argument("--bg-image-position", type=str, default="center center", help='CSS-ish position for background image cover crop. Default: "center center"')

    return p.parse_args()


def main() -> int:
    args = parse_args()

    font_path = args.font.resolve() if args.font else find_default_font().resolve()
    text_path = args.text.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ext = args.ext.lower().lstrip(".")
    if ext not in {"mp4", "mov", "m4v", "webm", "gif"}:
        raise SystemExit(f"Unsupported --ext: {args.ext}")

    if not font_path.exists():
        raise SystemExit(f"Font not found: {font_path}")

    text = read_text_file(text_path)
    if not text.strip():
        raise SystemExit(f"Text file is empty: {text_path}")

    axes = validate_variable_font(font_path)
    if "wdth" not in axes or "hght" not in axes:
        raise SystemExit(f"Expected wdth and hght axes in: {font_path}")

    font_wd_min, _, font_wd_max = axes["wdth"]
    font_hg_min, _, font_hg_max = axes["hght"]

    wdth_min = float(args.wdth_min if args.wdth_min is not None else font_wd_min)
    wdth_max = float(args.wdth_max if args.wdth_max is not None else font_wd_max)
    hght_min = float(args.hght_min if args.hght_min is not None else font_hg_min)
    hght_max = float(args.hght_max if args.hght_max is not None else font_hg_max)

    if wdth_min > wdth_max:
        raise SystemExit("wdth-min cannot be greater than wdth-max")
    if hght_min > hght_max:
        raise SystemExit("hght-min cannot be greater than hght-max")

    wdth_vals, hght_vals = build_axis_sequence(
        states=DEFAULT_STATES,
        fps=args.fps,
        hold_s=args.hold,
        move_s=args.move,
        wdth_min=wdth_min,
        wdth_max=wdth_max,
        hght_min=hght_min,
        hght_max=hght_max,
    )

    n_frames = int(wdth_vals.shape[0])
    duration_s = n_frames / float(args.fps)

    filename_source = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()
    slug = slugify_text(filename_source)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"{slug}-{timestamp}.{ext}"

    # Prepare stable full-canvas layers once.
    # This is the key to making the image NOT scale with the text.
    try:
        bg_layer = make_cover_layer(
            source=args.bg_image,
            out_w=args.width,
            out_h=args.height,
            position=args.bg_image_position,
            fallback_rgb=(255, 255, 255),
        )
        text_layer = make_cover_layer(
            source=args.text_image,
            out_w=args.width,
            out_h=args.height,
            position=args.text_image_position,
            fallback_rgb=(0, 0, 0),
        )
    except Exception as exc:
        raise SystemExit(f"Failed to prepare image layer: {exc}") from exc

    print(f"Using font:           {font_path}")
    print(f"Using text file:      {text_path}")
    print(f"Output:               {out_path}")
    print(f"Canvas:               {args.width}x{args.height}")
    print(f"FPS:                  {args.fps}")
    print(f"Font size:            {args.font_px}px")
    print(f"Line height:          {args.line_height}")
    print(f"wdth range:           {wdth_min:g} .. {wdth_max:g}")
    print(f"hght range:           {hght_min:g} .. {hght_max:g}")
    print(f"Frames:               {n_frames}")
    print(f"Duration:             {duration_s:.2f}s")
    print(f"Text image:           {args.text_image or '(solid black)'}")
    print(f"Text image position:  {args.text_image_position}")
    print(f"BG image:             {args.bg_image or '(solid white)'}")
    print(f"BG image position:    {args.bg_image_position}")
    print()
    print("Rendered text:")
    print("-" * 40)
    print(text.rstrip("\n"))
    print("-" * 40)

    writer = make_writer(out_path, fps=args.fps)

    try:
        for i in tqdm(range(n_frames), desc="Rendering"):
            inst_path = instance_font_path(
                base_font_path=font_path,
                wdth=float(wdth_vals[i]),
                hght=float(hght_vals[i]),
                wdth_min=wdth_min,
                wdth_max=wdth_max,
                hght_min=hght_min,
                hght_max=hght_max,
                round_to=args.round_to,
                cache_max=args.cache_max,
            )

            text_mask = render_text_mask_centered(
                inst_path=inst_path,
                text=text,
                font_px=args.font_px,
                W=args.width,
                H=args.height,
                line_height=args.line_height,
            )

            frame = composite_frame(
                text_mask=text_mask,
                bg_layer=bg_layer,
                text_layer=text_layer,
            )

            writer.append_data(np.array(frame))
    finally:
        writer.close()

    print()
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())