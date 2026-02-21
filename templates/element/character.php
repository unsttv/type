<?php
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
        $cp = \IntlChar::ord($ch);
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
$svg = preg_replace('/^\s*<\?xml\b.*?\?>\s*/is', '', $svg, 1);

echo $svg;
