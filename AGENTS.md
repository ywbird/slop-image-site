# AGENTS.md

## What this repo is

Single-page image-site generator. `pages/index.xml` (XML + mini CSS) is laid
out with Pillow and rendered to `site/image.png` + `site/links.json`. A small
viewer (`site/index.html` + `link.js`) overlays the link rectangles or redirects
`?x,y` clicks. Python package `image_site`; console script `image-site`.

## Commands

Run from the repo root; build paths are cwd-relative.

- Setup: `uv sync`
- Build: `uv run image-site build` (defaults `pages/index.xml` -> `site/`)
- Preview: `python -m http.server 8000 -d site`
- All tests: `uv run python -m unittest discover -s tests -v`
- One test: `uv run python -m unittest discover -s tests -v -k test_name`
- Typecheck: `uv run mypy src`
- Package: `uv build`

There is no lint, formatter, pytest, or CI config. Do not assume they exist.

## Git workflow

- Commit whenever changes are made.
- Push after completing each major task.

## Pipeline

`document.py` parses XML and resolves the mini CSS -> `layout.py` performs flow
layout and emits link rects -> `render.py` draws with Pillow -> `__init__.py`
writes the build and copies the viewer. Viewer templates live in
`src/image_site/viewer/`; `site/index.html` and `site/link.js` are generated
copies. Edit the source templates and rebuild; never hand-edit the copies.

## Constraints that will bite

- The CSS is a strict subset, not real CSS. Unknown tags, properties, or
  selectors, mixed block+inline content, missing fonts, and unsupported URL
  schemes fail the build. Read README before extending the DSL.
- Font `src` paths resolve relative to the XML file (`pages/index.xml` uses
  `../assets/fonts/...`). Every real text run must inherit or declare a
  `font-family` registered in `<fonts>`.
- Bundled Courier Code has no Korean glyphs. Use English or add a font.
- Layout is flow-only: vertical block stack, wrapping inline text, no absolute
  positioning, images, borders, or gradients. Margins do not collapse.
- `image.png` and `links.json` are a pair. Rebuild; do not edit one by hand.
- Link rects are listed in document order and later-drawn wins. The viewer
  paints forward; the `?x,y` redirector scans backward. Preserve both behaviors.
- `links.json` coordinates are intrinsic PNG pixels. `ismap` sends displayed
  CSS pixels, so the README `width` must equal the generated width. CSS shrinking
  (mobile) breaks direct ismap clicks; the viewer link is the fallback.
- Output PNGs are RGB and opaque; transparent colors are rejected intentionally.
- The viewer uses `fetch("links.json")`, so `file://` shows the image without
  links. Serve `site/` over HTTP.

## Publishing

`main` holds source plus generated `site/`. GitHub Pages serves the orphan
`gh-pages` branch whose root is the *contents* of `site/`, not the `site/`
directory. Live: <https://ywbird.github.io/slop-image-site/>. Update procedure
is in README's GitHub Pages section. Do not merge `gh-pages` into `main`; do not
forget to rebuild and push both branches when rendering or link output changes.
The build writes `.nojekyll` so Pages bypasses Jekyll.

## Verification gaps

There are no automated tests for the viewer/JS or browser click behavior.
After changing viewer code or link coordinates, serve `site/` and check direct
load (SVG overlay), `?x,y` redirect, narrow-viewport scaling, and the
later-link-wins overlap rule. `uv build` relies on
`[tool.uv.build-backend] module-name = "image_site"` because the project name
(`slop-image-site`) differs; keep it or the wheel build fails.
