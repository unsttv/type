<?php
/**
 * Auto-generated UNST SVG element for "ch"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-ch');
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
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 30" width="28" height="30" shape-rendering="crispEdges" class="unst unst-ch <?= htmlspecialchars($class, ENT_QUOTES) ?>"<?= $attr_str ?>>
  <g>
    <polygon class="ch" points="0,9 12,9 12,10 0,10"/>
    <polygon class="ch" points="0,10 4,10 4,19 0,19"/>
    <polygon class="ch" points="0,19 12,19 12,20 0,20"/>
    <polygon class="ch" points="16,0 20,0 20,20 16,20"/>
    <polygon class="ch" points="16,9 28,9 28,10 16,10"/>
    <polygon class="ch" points="24,10 28,10 28,20 24,20"/>
    <polygon class="ch" points="11,0 12,0 12,10 11,10"/>
    <polygon class="ch" points="11,0 17,0 17,1 11,1"/>
  </g>
</svg>

