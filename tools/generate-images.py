#!/usr/bin/env python3
"""
Render SVG glyphs from ./src into PNGs at ./dist/images with filenames:

  dist/images/unst-{character}.png

Input files are expected as:
  src/character-{character}.svg

This script is meant to live in a subfolder (e.g. ./tools/), so project root
is computed as: <this_file_dir>/..

Backends:
- Preferred: CairoSVG (pip install cairosvg)
- Fallback: Inkscape CLI (if installed)

Examples:
  python tools/render_glyph_pngs.py
  python tools/render_glyph_pngs.py --height 512
  python tools/render_glyph_pngs.py --backend inkscape --height 256
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# Optional CairoSVG backend
try:
    import cairosvg  # type: ignore
except Exception:
    cairosvg = None


VIEWBOX_RE = re.compile(r"viewBox\s*=\s*\"([0-9.+-eE]+)\s+([0-9.+-eE]+)\s+([0-9.+-eE]+)\s+([0-9.+-eE]+)\"")


@dataclass(frozen=True)
class ViewBox:
    x: float
    y: float
    w: float
    h: float


def project_root() -> Path:
    # Script is in a subfolder => project root is one directory up from script folder
    return Path(__file__).resolve().parent.parent


def parse_viewbox(svg_text: str) -> Optional[ViewBox]:
    m = VIEWBOX_RE.search(svg_text)
    if not m:
        return None
    x, y, w, h = map(float, m.groups())
    return ViewBox(x, y, w, h)


def ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def render_with_cairosvg(svg_path: Path, png_path: Path, out_height: int) -> None:
    if cairosvg is None:
        raise RuntimeError("CairoSVG is not available. Install with: pip install cairosvg")

    svg_text = svg_path.read_text(encoding="utf-8")
    vb = parse_viewbox(svg_text)
    if vb is None or vb.h <= 0:
        # reasonable fallback
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_height=out_height)
        return

    scale = out_height / vb.h
    out_width = max(1, int(round(vb.w * scale)))

    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=out_width,
        output_height=out_height,
    )


def render_with_inkscape(svg_path: Path, png_path: Path, out_height: int) -> None:
    inkscape = shutil.which("inkscape")
    if not inkscape:
        raise RuntimeError("Inkscape CLI not found on PATH.")

    # Inkscape will keep aspect ratio if only height is provided.
    cmd = [
        inkscape,
        str(svg_path),
        "--export-type=png",
        f"--export-filename={png_path}",
        f"--export-height={out_height}",
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def pick_backend(requested: str) -> str:
    requested = requested.lower().strip()
    if requested in ("cairosvg", "inkscape", "auto"):
        pass
    else:
        raise ValueError("backend must be one of: auto, cairosvg, inkscape")

    if requested == "cairosvg":
        return "cairosvg"
    if requested == "inkscape":
        return "inkscape"

    # auto
    if cairosvg is not None:
        return "cairosvg"
    if shutil.which("inkscape"):
        return "inkscape"
    return "none"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--height", type=int, default=512, help="Output PNG height in pixels (default: 512)")
    ap.add_argument("--backend", choices=["auto", "cairosvg", "inkscape"], default="auto")
    ap.add_argument("--src-dir", default="src", help="Source dir (relative to project root)")
    ap.add_argument("--dist-dir", default="dist/images", help="Output dir (relative to project root)")
    args = ap.parse_args()

    root = project_root()
    src_dir = (root / args.src_dir).resolve()
    out_dir = (root / args.dist_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = pick_backend(args.backend)
    if backend == "none":
        raise SystemExit(
            "No renderer available.\n"
            "- Install CairoSVG: pip install cairosvg\n"
            "  OR\n"
            "- Install Inkscape and ensure 'inkscape' is on your PATH."
        )

    svgs = sorted(src_dir.glob("character-*.svg"))
    if not svgs:
        raise SystemExit(f"No input SVGs found in: {src_dir} (expected files like character-a.svg)")

    ok = 0
    for svg_path in svgs:
        ch = svg_path.stem.replace("character-", "", 1)
        if not ch:
            continue

        png_path = out_dir / f"unst-{ch}.png"
        ensure_parent_dir(png_path)

        if backend == "cairosvg":
            render_with_cairosvg(svg_path, png_path, args.height)
        else:
            render_with_inkscape(svg_path, png_path, args.height)

        ok += 1

    print(f"Rendered {ok} PNGs with {backend} to: {out_dir}")


if __name__ == "__main__":
    main()
