#!/usr/bin/env python3
"""
Generate per-character templates from ./src/character-*.svg

Outputs:
1) templates/element/unst-{character}.php          (INLINE SVG)
2) templates/_unst-{character}.svg.twig           (INLINE SVG)

Assumptions:
- This script lives in a subfolder (e.g. ./tools/), so project root is: script_dir/..
- Source SVGs exist as: src/character-{ch}.svg
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Tuple

XML_DECL_RE = re.compile(r"^\s*<\?xml\b.*?\?>\s*$", re.IGNORECASE)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_svg_strip_xml(svg_path: Path) -> str:
    txt = svg_path.read_text(encoding="utf-8")
    lines = [ln for ln in txt.splitlines() if not XML_DECL_RE.match(ln)]
    return "\n".join(lines).strip() + "\n"


def split_svg_open_tag(svg_text: str) -> Tuple[str, str, str]:
    """
    Returns: (prefix_before_<svg, open_tag_including_>, suffix_after_open_tag)
    """
    i = svg_text.lower().find("<svg")
    if i < 0:
        raise ValueError("No <svg> tag found")

    j = svg_text.find(">", i)
    if j < 0:
        raise ValueError("Malformed SVG: no closing '>' for <svg ...>")

    return svg_text[:i], svg_text[i : j + 1], svg_text[j + 1 :]


def remove_attr(open_tag: str, attr_name: str) -> str:
    """
    Removes attr_name="..." or attr_name='...' from the open tag (best-effort).
    """
    # remove e.g.  class="..."  or class='...'
    pat = re.compile(rf"""\s+{re.escape(attr_name)}\s*=\s*(["']).*?\1""", re.IGNORECASE | re.DOTALL)
    return pat.sub("", open_tag, count=1)


def inject_twig_svg(open_tag: str, ch: str) -> str:
    """
    Ensure root <svg> has:
      class="unst unst-{ch} {% if class is defined and class %}{{ class }}{% endif %}"
    and optional attrs:
      {% if attrs is defined and attrs %} {{ attrs|raw }}{% endif %}
    """
    open_tag = remove_attr(open_tag, "class")

    # insert before the closing '>'
    if not open_tag.endswith(">"):
        raise ValueError("Open tag does not end with '>'")

    class_attr = (
        f' class="unst unst-{ch}'
        f'{{% if class is defined and class %}} {{ {{ class }} }}{{% endif %}}"'
    )
    attrs_hook = '{% if attrs is defined and attrs %} {{ attrs|raw }}{% endif %}'

    return open_tag[:-1] + class_attr + " " + attrs_hook + ">"


def inject_php_svg(open_tag: str, ch: str) -> str:
    """
    Ensure root <svg> has:
      class="unst unst-{ch} <?= htmlspecialchars($class, ENT_QUOTES) ?>"
      <?= $attr_str ?>
    """
    open_tag = remove_attr(open_tag, "class")

    if not open_tag.endswith(">"):
        raise ValueError("Open tag does not end with '>'")

    class_attr = f' class="unst unst-{ch} <?= htmlspecialchars($class, ENT_QUOTES) ?>"'
    attrs_hook = "<?= $attr_str ?>"

    return open_tag[:-1] + class_attr + attrs_hook + ">"


def php_element_template(ch: str, svg_inline: str) -> str:
    """
    $class (string) optional extra classes
    $attrs (array) optional extra svg attributes, e.g. ['aria-hidden' => 'true', 'role' => 'img', 'class' => '...']
    """
    return f"""<?php
/**
 * Auto-generated UNST SVG element for "{ch}"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-{ch}');
 *
 * Variables:
 *   - $class (string) extra classes to append
 *   - $attrs (array)  extra SVG attributes (key => value). Use true for boolean attrs.
 */
$class = trim((string)($class ?? ''));

// Allow class via $attrs too (merged)
$attrs = $attrs ?? [];
if (is_array($attrs) && isset($attrs['class'])) {{
    $class = trim($class . ' ' . (string)$attrs['class']);
    unset($attrs['class']);
}}

// Build attribute string for SVG root
$attr_str = '';
if (is_array($attrs)) {{
    foreach ($attrs as $k => $v) {{
        if ($v === null || $v === false) continue;
        $k_esc = htmlspecialchars((string)$k, ENT_QUOTES);
        if ($v === true) {{
            $attr_str .= ' ' . $k_esc;
            continue;
        }}
        $v_esc = htmlspecialchars((string)$v, ENT_QUOTES);
        $attr_str .= ' ' . $k_esc . '="' . $v_esc . '"';
    }}
}}
?>
{svg_inline}
"""


def main() -> None:
    root = project_root()

    src_dir = root / "src"
    php_dir = root / "templates" / "element"
    twig_dir = root / "templates"

    php_dir.mkdir(parents=True, exist_ok=True)
    twig_dir.mkdir(parents=True, exist_ok=True)

    svgs = sorted(src_dir.glob("character-*.svg"))
    if not svgs:
        raise SystemExit(f"No SVGs found in {src_dir} (expected src/character-*.svg)")

    count = 0
    for svg_path in svgs:
        ch = svg_path.stem.replace("character-", "", 1)
        if not ch:
            continue

        svg_text = read_svg_strip_xml(svg_path)
        prefix, open_tag, suffix = split_svg_open_tag(svg_text)

        # --- Twig SVG partial ---
        twig_open = inject_twig_svg(open_tag, ch)
        twig_svg = prefix + twig_open + suffix
        twig_path = twig_dir / f"_unst-{ch}.svg.twig"
        twig_path.write_text(
            "{# Auto-generated. Edit /src/character-*.svg if needed. #}\n" + twig_svg,
            encoding="utf-8",
        )

        # --- PHP element (INLINE SVG) ---
        php_open = inject_php_svg(open_tag, ch)
        php_svg = prefix + php_open + suffix
        php_path = php_dir / f"unst-{ch}.php"
        php_path.write_text(php_element_template(ch, php_svg), encoding="utf-8")

        count += 1

    print(f"Generated {count} PHP inline-SVG elements in: {php_dir}")
    print(f"Generated {count} Twig inline-SVG partials in: {twig_dir}")


if __name__ == "__main__":
    main()
