# slop image site

**A website rendered to one PNG, with links that still work.**

Click the links in the image below. On mobile or with a keyboard,
[open the interactive viewer](https://ywbird.github.io/slop-image-site/) instead.

<a href="https://ywbird.github.io/slop-image-site/">
  <img ismap width="600" height="431" src="https://ywbird.github.io/slop-image-site/image.png" alt="slop image site demo: source and meliplug.info links inside this PNG">
</a>

[Build](#build) · [README embed](#readme-embed) · [Source format](#source-format) · [Project notes](#project-notes)

## From XML to clicks

Write a small XML document with a mini CSS dialect. Pillow lays out the text
and draws the page; the build also records where each link belongs.

```text
pages/index.xml
      │  layout + render with Pillow
      ├── image.png     visible page
      └── links.json    link rectangles
```

A tiny HTML/JS viewer overlays the link rectangles on the image. It also
handles the `?x,y` coordinates sent by an `ismap` image in a README, redirecting
the click to its destination. The page's appearance is a bitmap, not a browser
layout; the viewer supplies the interaction.

The earlier [image-site proof of concept (PoC)](https://codeberg.org/ywbird/image-site)
lives on Codeberg. This repository is the AI:X slop implementation.

## Build

```sh
uv sync
uv run image-site build
```

By default, `pages/index.xml` builds into `site/`:

```text
site/
├── image.png
├── links.json
├── index.html
├── link.js
└── .nojekyll
```

### Local preview

```sh
python -m http.server 8000 -d site
```

Open <http://localhost:8000/>.

### Tests and types

```sh
uv run python -m unittest discover -s tests -v
uv run mypy src
```

## README embed

Host the `site/` directory, then put this in a README. Keep the `width` equal
to the generated image width so coordinates match.

```html
<a href="https://example.com/site/">
  <img ismap width="600" src="https://example.com/site/image.png" alt="slop image site">
</a>

<a href="https://example.com/site/">open viewer</a>
```

Clicks send `?x,y` to the viewer, which redirects to the matching link. If no
link matches, the browser goes back to the page that showed the image (a blank
area is a "return" click); with no history to return to, the viewer is shown.
The viewer is also the keyboard and mobile
entry point.

> **Caveat:** `ismap` coordinates are measured in *displayed* CSS pixels.
> Codeberg/GitHub CSS can shrink a wide image on narrow screens, which would
> offset the hitboxes. The viewer itself is responsive and uses an SVG overlay,
> so link a "view full size" viewer below the README image for mobile.
>
> Codeberg keeps `ismap`, `width` and `height` on README images (verified).
> Other hosts may sanitize `ismap` away.

## Source format

`pages/index.xml` is the page source. The root is `<page>`:

```xml
<page width="600" padding="48" background="#f2efe9" title="my page">
  <fonts>
    <font name="mono" src="../assets/fonts/CourierCode-Roman.ttf"/>
    <font name="mono-bold" src="../assets/fonts/CourierCode-Bold.ttf"/>
  </fonts>

  <style>
    page { font-family: mono; font-size: 18; color: #242424; line-height: 1.6; }
    h1 { font-family: mono-bold; font-size: 38; margin: 0 0 28 0; }
    p { margin: 0 0 18 0; }
    a { color: #0a58ca; text-decoration: underline; }
    .muted { color: #7a756c; font-size: 14; }
  </style>

  <h1>hello</h1>
  <p>this is a <a href="https://example.com">link</a>.</p>
</page>
```

Font paths are resolved relative to the XML file. If `height` is omitted the
page grows to fit its content. `width`, `height`, `padding`, `background` and
`title` are page attributes, not CSS properties.

### Elements

| Element | Behaviour |
| --- | --- |
| `page` | root, fixed width, optional height |
| `div` | block, may contain blocks or inline content (not both) |
| `p`, `h1`, `h2`, `h3` | block, inline content only |
| `span` | inline, style only |
| `a` | inline link, `href` required |
| `br` | forced line break |

Blocks stack vertically. Paragraphs wrap to the page width. Margins do not
collapse. A link spanning multiple lines gets one hitbox per line.

### Style subset

Selectors: `tag`, `.class`, `#id`, `tag.class`, and comma-separated lists.
There are no descendant selectors, pseudo-classes, or media queries.

Properties:

| Property | Values |
| --- | --- |
| `font-family` | a name declared in `<fonts>` |
| `font-size` | integer px |
| `color` | CSS color name or hex |
| `line-height` | unitless number |
| `text-align` | `left`, `center`, `right` |
| `text-decoration` | `underline`, `none` |
| `background` | color or `none` |
| `margin`, `margin-*` | px, 1–4 values |
| `padding`, `padding-*` | px, 1–4 values |

Text properties inherit. `background`, `margin` and `padding` do not. There is
no `font-weight`; declare a separate font name for bold. `background`, `margin`
and `padding` only affect block elements in this renderer.

### Links

Link rectangles are written in document order. When two rectangles overlap,
the one drawn later wins. The viewer paints them in document order (later on
top), and the `?x,y` redirector scans the list in reverse.

Supported link schemes: `http`, `https`, `mailto`, and relative URLs.
`javascript:` and other schemes are rejected at build time.

## Limits

- No embedded images, borders, gradients, absolute positioning, lists, or
  tables yet.
- Colors are opaque; transparent colors are rejected.
- Fonts must include every glyph you use. The bundled Courier Code has no
  Korean glyphs.
- The generated page is one fixed-width bitmap; text does not reflow after
  build.
- `site/` is generated output. Commit it if the README embeds the PNG, and
  re-run the build whenever `pages/index.xml` changes.

## GitHub Pages

`main` holds the source. `gh-pages` is an orphan branch whose root is the
contents of `site/`, so the built viewer is published directly:

<https://ywbird.github.io/slop-image-site/>

GitHub Pages source should be `gh-pages` / `/ (root)`. To update the published
branch after a rebuild:

```sh
uv run image-site build
git worktree add /tmp/slop-pages gh-pages
cp -a site/. /tmp/slop-pages/
git -C /tmp/slop-pages add -A
git -C /tmp/slop-pages commit -m "publish site"
git -C /tmp/slop-pages push origin gh-pages
git worktree remove /tmp/slop-pages
```

The generated `.nojekyll` keeps Pages from running Jekyll.

## Deploy

Copy `site/` to any static host. The README image and `site/links.json` must be
regenerated together; keep caching disabled or revalidated for both so stale
coordinates are not served with a new image.

## Project notes

### AI usage

<a href="https://0rwx.com/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/readme/AI-X-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/readme/AI-X-light.svg">
    <img src="assets/readme/AI-X-light.svg" width="64" height="64" alt="AI:X — Execute, AI-made">
  </picture>
</a>

**AI:X — Execute / AI-made**, using the [0rwx framework](https://0rwx.com/).
The author delegates implementation to AI without personally reviewing the
generated code. The `slop-` prefix makes that distinction explicit.

The official AI:X marks are included unchanged from 0rwx.com and are
[CC0 / public domain](https://creativecommons.org/publicdomain/zero/1.0/).

### Fonts

Courier Code is included under `assets/fonts/`. See
`assets/fonts/Courier Code Read Me.txt`; the license permits redistribution.
