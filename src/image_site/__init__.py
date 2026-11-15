from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Sequence

from .document import DocumentError, Page, parse_document
from .fonts import FontBook
from .layout import Layout, layout_page
from .render import render


VIEWER_FILES = ("index.html", "link.js")


def build(source: Path, out: Path) -> tuple[Page, Layout]:
    page = parse_document(source)
    fonts = FontBook(page.fonts)
    layout = layout_page(page, fonts)
    image = render(layout, fonts)

    out.mkdir(parents=True, exist_ok=True)
    image.save(out / "image.png", "PNG")

    payload = {
        "title": page.title,
        "width": layout.width,
        "height": layout.height,
        "links": [
            {
                "href": link.href,
                "label": link.label,
                "left": link.left,
                "top": link.top,
                "right": link.right,
                "bottom": link.bottom,
            }
            for link in layout.links
        ],
    }
    (out / "links.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    viewer = Path(__file__).with_name("viewer")
    for name in VIEWER_FILES:
        shutil.copyfile(viewer / name, out / name)
    # GitHub Pages: serve files as-is instead of running Jekyll.
    (out / ".nojekyll").write_text("", encoding="utf-8")

    return page, layout


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="image-site",
        description="Render an XML page to a PNG with a clickable link map.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="render a page")
    build_parser.add_argument(
        "source",
        nargs="?",
        default=Path("pages/index.xml"),
        type=Path,
        help="XML source (default: pages/index.xml)",
    )
    build_parser.add_argument(
        "-o",
        "--out",
        default=Path("site"),
        type=Path,
        help="output directory (default: site)",
    )

    args = parser.parse_args(argv)
    if args.command != "build":
        parser.error(f"unknown command {args.command}")

    try:
        page, layout = build(args.source, args.out)
    except (DocumentError, OSError) as exc:
        parser.exit(1, f"image-site: {exc}\n")

    print(f"built {layout.width}x{layout.height}, {len(layout.links)} link(s)")
    print(f"  {args.out / 'image.png'}")
    print(f"  {args.out / 'links.json'}")
    for name in VIEWER_FILES:
        print(f"  {args.out / name}")
    print(f"  title: {page.title}")


if __name__ == "__main__":
    main()
