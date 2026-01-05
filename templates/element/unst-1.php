<?php
/**
 * Auto-generated UNST SVG element for "1"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-1');
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
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 30" width="12" height="30" shape-rendering="crispEdges" class="unst unst-1 <?= htmlspecialchars($class, ENT_QUOTES) ?>"<?= $attr_str ?>>
  <g>
    <polygon class="1" points="4,9 12,9 12,10 4,10"/>
    <polygon class="1" points="8,10 12,10 12,20 8,20"/>
    <polygon class="1" points="4,19 12,19 12,20 4,20"/>
  </g>
</svg>

