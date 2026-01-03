<?php
/**
 * Auto-generated UNST SVG element for "a"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-a');
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
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 30" shape-rendering="crispEdges" class="unst unst-a <?= htmlspecialchars($class, ENT_QUOTES) ?>"<?= $attr_str ?>>
  <g>
    <polygon class="a" points="12,20 0,20 0,19 12,19"/>
    <polygon class="a" points="12,19 8,19 8,10 12,10"/>
    <polygon class="a" points="4,19 0,19 0,15 4,15"/>
    <polygon class="a" points="12,15 0,15 0,14 12,14"/>
    <polygon class="a" points="12,10 0,10 0,9 12,9"/>
  </g>
</svg>

