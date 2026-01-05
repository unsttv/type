<?php
/**
 * Auto-generated UNST SVG element for "sh"
 *
 * Usage (CakePHP):
 *   echo $this->element('unst-sh');
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
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 30" width="32" height="30" shape-rendering="crispEdges" class="unst unst-sh <?= htmlspecialchars($class, ENT_QUOTES) ?>"<?= $attr_str ?>>
  <g>
    <polygon class="sh" points="0,9 12,9 12,10 0,10"/>
    <polygon class="sh" points="0,10 4,10 4,14 0,14"/>
    <polygon class="sh" points="0,14 12,14 12,15 0,15"/>
    <polygon class="sh" points="8,15 12,15 12,19 8,19"/>
    <polygon class="sh" points="0,19 12,19 12,20 0,20"/>
    <polygon class="sh" points="20,0 24,0 24,20 20,20"/>
    <polygon class="sh" points="20,9 32,9 32,10 20,10"/>
    <polygon class="sh" points="28,10 32,10 32,20 28,20"/>
    <polygon class="sh" points="12,1 13,1 13,10 12,10"/>
    <polygon class="sh" points="12,0 21,0 21,1 12,1"/>
  </g>
</svg>

