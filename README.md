
# unst Type

## Letter Sample

![a](src/character-a.svg)![b](src/character-b.svg)![c](src/character-c.svg)![d](src/character-d.svg)![e](src/character-e.svg)![f](src/character-f.svg)![g](src/character-g.svg)![h](src/character-h.svg)![i](src/character-i.svg)![j](src/character-j.svg)![k](src/character-k.svg)![l](src/character-l.svg)![m](src/character-m.svg)![n](src/character-n.svg)![o](src/character-o.svg)![p](src/character-p.svg)![q](src/character-q.svg)![r](src/character-r.svg)![s](src/character-s.svg)![t](src/character-t.svg)![u](src/character-u.svg)![v](src/character-v.svg)![w](src/character-w.svg)![x](src/character-x.svg)![y](src/character-y.svg)![z](src/character-z.svg)![0](src/character-0.svg)![1](src/character-1.svg)![2](src/character-2.svg)![3](src/character-3.svg)![4](src/character-4.svg)![5](src/character-5.svg)![6](src/character-6.svg)![7](src/character-7.svg)![8](src/character-8.svg)![9](src/character-9.svg)

## Grid

![Grid](src/grid.svg)

## Usage

```css
@font-face {
  font-family: "unst";
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src:
    url("https://hetcdn.nl/fonts/unst.woff2") format("woff2"),
    url("https://hetcdn.nl/fonts/unst.woff") format("woff"),
    url("https://hetcdn.nl/fonts/unst.ttf") format("truetype");
}

:root {
    --font--unst: "unst", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
}

.font--unst {
  font-family: var(--font--unst);
  font-weight: 400;
  font-style: normal;
}
```

## Add glyphs

1. Design new glyph using the [glyph designer](tools/glyph-designer.html).
2. Save SVG to ``src``.
3. Run `py tools\generate-data.py`.
4. Run `py tools\generate-fonts.py`.
5. Run `py tools\generate-manifest.py`.
