#!/usr/bin/env python3
"""
Generate shared character templates for UNST.

Outputs:
1) templates/element/character.php      (CakePHP element, reads SVG from ./src at runtime)
2) templates/_character.svg.twig        (Twig partial, reads SVG via Twig `source()` from a Twig path alias)
3) templates/_letter-sample.md.twig     (Markdown Twig partial: one image per line for ALL glyphs in ./src)

Filename schemes supported in ./src:
- New:
    character-uXXXX.svg
    ligature-uXXXX-uYYYY.svg
- Legacy (fallback while migrating):
    character-a.svg
    character-A-cap.svg
    character-st.svg

Assumptions:
- This script lives in a subfolder (e.g. ./tools/), so project root is: script_dir/..
- Source SVGs exist in: ./src
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple


# New filename patterns
RE_NEW_SINGLE = re.compile(r"^character-u([0-9a-fA-F]{1,8})\.svg$")
RE_NEW_LIGA = re.compile(r"^ligature-((?:u[0-9a-fA-F]{1,8})(?:-u[0-9a-fA-F]{1,8})+)\.svg$")

# Legacy filename patterns (kept for migration friendliness)
RE_OLD_CAP = re.compile(r"^character-(.)-cap\.svg$")
RE_OLD_CHAR = re.compile(r"^character-(.+)\.svg$")


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def decode_svg_filename_to_key(filename: str) -> Optional[str]:
    """
    Convert a source SVG filename into the glyph key string:
      character-u0061.svg        -> "a"
      ligature-u0073-u0074.svg   -> "st"
      character-A-cap.svg        -> "A"   (legacy)
      character-st.svg           -> "st"  (legacy)
    """
    m = RE_NEW_SINGLE.match(filename)
    if m:
        cp = int(m.group(1), 16)
        try:
            return chr(cp)
        except ValueError:
            return None

    m = RE_NEW_LIGA.match(filename)
    if m:
        parts = m.group(1).split("-")
        chars: List[str] = []
        for p in parts:
            cp = int(p[1:], 16)  # strip leading "u"
            try:
                chars.append(chr(cp))
            except ValueError:
                return None
        return "".join(chars)

    m = RE_OLD_CAP.match(filename)
    if m:
        return m.group(1)

    m = RE_OLD_CHAR.match(filename)
    if m:
        return m.group(1)

    return None


def collect_svg_map(src_dir: Path) -> Dict[str, str]:
    """
    Returns mapping:
      glyph_key -> source filename (basename only)

    If duplicates exist, prefer new filename scheme over legacy.
    """
    out: Dict[str, str] = {}

    files = sorted([p for p in src_dir.glob("*.svg") if p.is_file()], key=lambda p: p.name.lower())

    for p in files:
        key = decode_svg_filename_to_key(p.name)
        if not key:
            continue

        existing = out.get(key)
        if existing is None:
            out[key] = p.name
            continue

        is_new = bool(RE_NEW_SINGLE.match(p.name) or RE_NEW_LIGA.match(p.name))
        existing_is_new = bool(RE_NEW_SINGLE.match(existing) or RE_NEW_LIGA.match(existing))
        if is_new and not existing_is_new:
            out[key] = p.name

    return out


def key_sort_tuple(key: str) -> Tuple[int, Tuple[int, ...]]:
    return (len(key), tuple(ord(c) for c in key))


def twig_escape_single_quoted(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def build_twig_template(svg_map: Dict[str, str]) -> str:
    items = sorted(svg_map.items(), key=lambda kv: key_sort_tuple(kv[0]))
    map_lines = []
    for key, fname in items:
        map_lines.append(
            f"  '{twig_escape_single_quoted(key)}': '{twig_escape_single_quoted(fname)}',"
        )
    map_block = "\n".join(map_lines)

    return f"""{{# Auto-generated shared UNST character SVG partial. #}}
{{#
Usage (Twig / Symfony):
  {{% include '_character.svg.twig' with {{ character: 'a' }} %}}
  {{% include '_character.svg.twig' with {{ character: 'st' }} %}}

Optional:
  - svg_namespace: Twig path alias to the package's /src directory (default: '@unst_src')

Expected Twig config (example):
  twig:
    paths:
      '%kernel.project_dir%/vendor/<vendor>/<package>/src': unst_src
#}}

{{% set _unst_svg_namespace = svg_namespace|default('@unst_src') %}}
{{% set _unst_character = character|default('') %}}

{{% set _unst_svg_map = {{
{map_block}
}} %}}

{{% set _unst_file = attribute(_unst_svg_map, _unst_character)|default(null) %}}
{{% if _unst_file %}}
{{{{ source(_unst_svg_namespace ~ '/' ~ _unst_file, true)
    |replace({{
        '<?xml version="1.0" encoding="utf-8"?>\\n': '',
        '<?xml version="1.0" encoding="utf-8"?>': ''
    }})
    |raw }}}}
{{% endif %}}
"""


def build_cake_template() -> str:
    return """<?php
/**
 * Auto-generated shared UNST SVG element.
 *
 * Usage (CakePHP):
 *   echo $this->element('character', ['character' => 'a']);
 *   echo $this->element('character', ['character' => 'st']);
 *
 * Variables:
 *   - $character (string) required; single glyph char or ligature key (e.g. "st")
 */

$character = (string)($character ?? '');
if ($character === '') {
    return;
}

/**
 * Split UTF-8 string into chars.
 *
 * @return list<string>
 */
$unst_split_chars = static function (string $s): array {
    $parts = preg_split('//u', $s, -1, PREG_SPLIT_NO_EMPTY);
    return is_array($parts) ? $parts : [];
};

/**
 * Convert one UTF-8 character to lowercase hex codepoint (min 4 digits), e.g. "A" => "0041".
 */
$unst_codepoint_hex = static function (string $ch): ?string {
    $cp = null;

    if (function_exists('mb_ord')) {
        $cp = mb_ord($ch, 'UTF-8');
    } elseif (class_exists('IntlChar')) {
        $cp = \\IntlChar::ord($ch);
    } else {
        // Fallback: only works for single-byte chars
        $bytes = @unpack('C*', $ch);
        if (is_array($bytes) && count($bytes) === 1) {
            $cp = (int)array_values($bytes)[0];
        }
    }

    if (!is_int($cp) || $cp < 0) {
        return null;
    }

    $hex = strtolower(dechex($cp));
    return str_pad($hex, 4, '0', STR_PAD_LEFT);
};

$chars = $unst_split_chars($character);
if (!$chars) {
    return;
}

$hexes = [];
foreach ($chars as $ch) {
    $hx = $unst_codepoint_hex($ch);
    if ($hx === null) {
        return;
    }
    $hexes[] = $hx;
}

if (count($hexes) === 1) {
    $filename = 'character-u' . $hexes[0] . '.svg';
} else {
    $parts = [];
    foreach ($hexes as $hx) {
        $parts[] = 'u' . $hx;
    }
    $filename = 'ligature-' . implode('-', $parts) . '.svg';
}

// templates/element/character.php -> project root is two levels up
$srcDir = dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . 'src';
$svgPath = $srcDir . DIRECTORY_SEPARATOR . $filename;

if (!is_file($svgPath) || !is_readable($svgPath)) {
    return;
}

$svg = @file_get_contents($svgPath);
if ($svg === false) {
    return;
}

// Strip XML declaration for inline SVG usage in HTML
$svg = preg_replace('/^\\s*<\\?xml\\b.*?\\?>\\s*/is', '', $svg, 1);

echo $svg;
"""


def _md_alt_for_key(key: str) -> str:
    if key == " ":
        return "SPACE"
    if key == "\t":
        return "TAB"
    if key == "\n":
        return "LF"
    return key


def _md_escape_alt(s: str) -> str:
    return s.replace("\\", "\\\\").replace("]", "\\]")


def build_letter_sample_md_twig(svg_map: Dict[str, str]) -> str:
    """
    Markdown: ONE image per line (newline-separated), i.e. readable source + visible spacing.

    Format:
      ![a](src/character-u0061.svg)
      ![b](src/character-u0062.svg)
      ...
    """
    singles = [(k, svg_map[k]) for k in svg_map.keys() if len(k) == 1]
    ligas = [(k, svg_map[k]) for k in svg_map.keys() if len(k) > 1]

    ordered: List[Tuple[str, str]] = []

    # Nice order for common sets first
    for ch in "abcdefghijklmnopqrstuvwxyz":
        if ch in svg_map and len(ch) == 1:
            ordered.append((ch, svg_map[ch]))
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if ch in svg_map and len(ch) == 1:
            ordered.append((ch, svg_map[ch]))
    for ch in "0123456789":
        if ch in svg_map and len(ch) == 1:
            ordered.append((ch, svg_map[ch]))

    already = set(k for k, _ in ordered)
    rest_singles = [(k, f) for (k, f) in singles if k not in already]
    rest_singles.sort(key=lambda kv: ord(kv[0]))
    ordered.extend(rest_singles)

    ligas.sort(key=lambda kv: key_sort_tuple(kv[0]))
    ordered.extend(ligas)

    lines: List[str] = []
    for key, fname in ordered:
        alt = _md_escape_alt(_md_alt_for_key(key))
        lines.append(f"![{alt}](src/{fname})")

    return "\n".join(lines) + "\n"


def main() -> None:
    root = project_root()

    src_dir = root / "src"
    php_dir = root / "templates" / "element"
    twig_dir = root / "templates"

    if not src_dir.exists():
        raise SystemExit(f"Source directory not found: {src_dir}")

    php_dir.mkdir(parents=True, exist_ok=True)
    twig_dir.mkdir(parents=True, exist_ok=True)

    svg_map = collect_svg_map(src_dir)
    if not svg_map:
        raise SystemExit(
            f"No supported SVG glyph files found in {src_dir} "
            "(expected character-uXXXX.svg / ligature-uXXXX-uYYYY.svg)"
        )

    twig_path = twig_dir / "_character.svg.twig"
    php_path = php_dir / "character.php"
    md_path = twig_dir / "_letter-sample.md.twig"

    twig_path.write_text(build_twig_template(svg_map), encoding="utf-8")
    php_path.write_text(build_cake_template(), encoding="utf-8")
    md_path.write_text(build_letter_sample_md_twig(svg_map), encoding="utf-8")

    single_count = sum(1 for k in svg_map if len(k) == 1)
    liga_count = sum(1 for k in svg_map if len(k) > 1)

    print(f"Wrote Twig template: {twig_path}")
    print(f"Wrote CakePHP template: {php_path}")
    print(f"Wrote Markdown Twig template: {md_path}")
    print(f"Indexed {len(svg_map)} glyphs from {src_dir} ({single_count} single, {liga_count} ligatures)")


if __name__ == "__main__":
    main()