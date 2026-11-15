from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from image_site import build
from image_site.document import DocumentError, Node, Page, parse_document
from image_site.fonts import FontBook
from image_site.layout import layout_page


ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "assets" / "fonts" / "CourierCode-Roman.ttf"


def xml_page(body: str, *, style: str = "", width: int = 300) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<page width="{width}" padding="10" background="#ffffff" title="test">\n'
        f'  <fonts><font name="mono" src="{FONT}"/></fonts>\n'
        f"  <style>{style}</style>\n"
        f"  {body}\n"
        "</page>\n"
    )


class PageCase(unittest.TestCase):
    def parse(self, body: str, *, style: str = "", width: int = 300) -> Page:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "page.xml"
        path.write_text(xml_page(body, style=style, width=width), encoding="utf-8")
        return parse_document(path)

    def layout(self, page: Page):
        return layout_page(page, FontBook(page.fonts))


class StyleTests(PageCase):
    def test_cascade_and_inheritance(self) -> None:
        page = self.parse(
            '<p class="note" id="last">hello</p>',
            style=(
                "page { font-family: mono; font-size: 10; color: #111111; }"
                "p { font-size: 20; color: #222222; }"
                ".note { color: #333333; }"
                "#last { color: #444444; }"
            ),
        )
        node = page.root.children[0]
        assert isinstance(node, Node)
        self.assertEqual(node.style.color, (0x44, 0x44, 0x44))
        self.assertEqual(node.style.font_size, 20)
        self.assertEqual(node.style.font_family, "mono")

    def test_javascript_href_is_rejected(self) -> None:
        with self.assertRaises(DocumentError):
            self.parse('<p><a href="javascript:alert(1)">bad</a></p>')

    def test_newline_in_href_is_rejected(self) -> None:
        with self.assertRaises(DocumentError):
            self.parse('<p><a href="java&#10;script:alert(1)">bad</a></p>')

    def test_mixed_block_and_inline_is_rejected(self) -> None:
        with self.assertRaises(DocumentError):
            self.parse("<div>text<p>block</p></div>")


class LayoutTests(PageCase):
    def test_long_link_wraps_into_multiple_rects(self) -> None:
        page = self.parse(
            '<p><a href="https://example.com">alpha beta gamma delta epsilon zeta eta theta</a></p>',
            style="page { font-family: mono; font-size: 14; }",
            width=220,
        )
        layout = self.layout(page)
        links = [link for link in layout.links if link.href == "https://example.com"]
        self.assertGreaterEqual(len(links), 2)
        self.assertEqual(links[0].label, "alpha beta gamma delta epsilon zeta eta theta")
        self.assertEqual([link.top for link in links], sorted(link.top for link in links))
        self.assertTrue(all(0 <= link.left < link.right <= 220 for link in links))

    def test_links_keep_document_order(self) -> None:
        page = self.parse(
            '<p><a href="https://one.example">one</a> and '
            '<a href="https://two.example">two</a></p>',
            style="page { font-family: mono; font-size: 14; }",
        )
        layout = self.layout(page)
        self.assertEqual(
            [link.href for link in layout.links],
            ["https://one.example", "https://two.example"],
        )

    def test_auto_height_and_fixed_height(self) -> None:
        body = '<p><a href="https://example.com">link</a></p>'
        style = "page { font-family: mono; font-size: 14; }"
        auto = self.parse(body, style=style)
        self.assertGreater(self.layout(auto).height, 20)

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "page.xml"
        path.write_text(
            xml_page(body, style=style).replace(
                'title="test"', 'title="test" height="80"'
            ),
            encoding="utf-8",
        )
        fixed = parse_document(path)
        self.assertEqual(self.layout(fixed).height, 80)


class BuildTests(PageCase):
    def test_build_writes_rgb_png_and_json(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name) / "page.xml"
        source.write_text(
            xml_page(
                '<p><a href="https://example.com">link</a></p>',
                style="page { font-family: mono; font-size: 14; }",
                width=300,
            ),
            encoding="utf-8",
        )
        out = Path(temporary.name) / "out"
        _, layout = build(source, out)

        data = json.loads((out / "links.json").read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "test")
        self.assertEqual(data["width"], layout.width)
        self.assertEqual(data["height"], layout.height)
        self.assertEqual(len(data["links"]), len(layout.links))

        image = Image.open(out / "image.png")
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (layout.width, layout.height))
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        self.assertNotEqual(image.getextrema(), ((255, 255, 255),) * 3)

        for name in ("index.html", "link.js", ".nojekyll"):
            self.assertTrue((out / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
