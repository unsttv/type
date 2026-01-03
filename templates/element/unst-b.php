<?php
/**
 * Auto-generated UNST SVG element for "b"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-b');
 *
 * Variables:
 *   - $class (string) extra classes to append
 *   - $attrs (array)  extra SVG attributes (key => value). Use true for boolean attrs.
 */
$class = trim((string)($class ?? ''));

// Allow class via $attrs too (merged)
$attrs = $attrs ?? [];
if (is_array($attrs) && isset($attrs['class'])) {
    $class = trim($class . ' ' . (string)$attrs['class']);
    unset($attrs['class']);
}

// Build attribute string for SVG root
$attr_str = '';
if (is_array($attrs)) {
    foreach ($attrs as $k => $v) {
        if ($v === null || $v === false) continue;
        $k_esc = htmlspecialchars((string)$k, ENT_QUOTES);
        if ($v === true) {
            $attr_str .= ' ' . $k_esc;
            continue;
        }
        $v_esc = htmlspecialchars((string)$v, ENT_QUOTES);
        $attr_str .= ' ' . $k_esc . '="' . $v_esc . '"';
    }
}
?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 30" shape-rendering="crispEdges" class="unst unst-b <?= htmlspecialchars($class, ENT_QUOTES) ?>"<?= $attr_str ?>>
  <g>
    <polygon class="b" points="0,0 4,0 4,20 0,20"/>
    <polygon class="b" points="4,9 12,9 12,10 4,10"/>
    <polygon class="b" points="8,10 12,10 12,19 8,19"/>
    <polygon class="b" points="4,19 12,19 12,20 4,20"/>
  </g>
</svg>

