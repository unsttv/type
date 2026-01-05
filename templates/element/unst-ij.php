<?php
/**
 * Auto-generated UNST SVG element for "ij"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-ij');
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
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 30" width="20" height="30" shape-rendering="crispEdges" class="unst unst-ij <?= htmlspecialchars($class, ENT_QUOTES) ?>"<?= $attr_str ?>>
  <g>
    <polygon class="ij" points="4,9 8,9 8,20 4,20"/>
    <polygon class="ij" points="4,0 8,0 8,4 4,4"/>
    <polygon class="ij" points="12,9 16,9 16,30 12,30"/>
    <polygon class="ij" points="12,0 16,0 16,4 12,4"/>
    <polygon class="ij" points="8,29 12,29 12,30 8,30"/>
  </g>
</svg>

