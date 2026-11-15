from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Sequence
from pathlib import Path
import re
from typing import cast
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from PIL import ImageColor


Color = tuple[int, int, int]


class DocumentError(ValueError):
    """Raised when the XML source cannot be turned into a page."""


@dataclass(frozen=True)
class Edges:
    top: int = 0
    right: int = 0
    bottom: int = 0
    left: int = 0


@dataclass(frozen=True)
class Style:
    font_family: str | None = None
    font_size: int = 16
    color: Color = (0, 0, 0)
    line_height: float = 1.4
    align: str = "left"
    underline: bool = False
    background: Color | None = None
    margin: Edges = Edges()
    padding: Edges = Edges()


DEFAULT_STYLE = Style()

BLOCK_TAGS = frozenset({"div", "p", "h1", "h2", "h3"})
INLINE_TAGS = frozenset({"span", "a", "br"})
ALLOWED_TAGS = BLOCK_TAGS | INLINE_TAGS


@dataclass(frozen=True)
class Text:
    value: str


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    style: Style
    children: Sequence[Node | Text]
    path: str


@dataclass(frozen=True)
class Selector:
    tag: str | None
    classes: frozenset[str]
    element_id: str | None
    specificity: tuple[int, int, int]

    def matches(self, tag: str, attrs: dict[str, str]) -> bool:
        if self.tag is not None and self.tag != tag:
            return False
        if self.element_id is not None and self.element_id != attrs.get("id"):
            return False
        if self.classes:
            node_classes = set(attrs.get("class", "").split())
            if not self.classes <= node_classes:
                return False
        return True


@dataclass(frozen=True)
class Rule:
    selector: Selector
    declarations: dict[str, object]
    order: int


@dataclass
class Page:
    title: str
    width: int
    height: int | None
    padding: int
    background: Color
    fonts: dict[str, Path]
    root: Node


# --------------------------------------------------------------------------
# XML parsing


def parse_document(source: Path) -> Page:
    source = source.resolve()
    try:
        tree = ET.parse(source)
    except ET.ParseError as exc:
        raise DocumentError(f"{source}: XML parse error: {exc}") from exc
    except OSError as exc:
        raise DocumentError(f"cannot read {source}: {exc}") from exc

    root = tree.getroot()
    if root.tag != "page":
        raise DocumentError(f"root element must be <page>, got <{root.tag}>")

    _check_attrs(
        root,
        {"width", "height", "padding", "background", "title", "class", "id"},
        "page",
    )

    width = _int_attr(root, "width", required=True, minimum=1)
    assert width is not None
    height = _int_attr(root, "height", required=False, minimum=1)
    padding = _int_attr(root, "padding", required=False, minimum=0) or 0
    background_attr = root.get("background")
    title = root.get("title", "image site")

    fonts = _parse_fonts(root, source.parent)
    rules = _parse_styles(root)
    style = _resolve_style(root, DEFAULT_STYLE, rules, fonts)
    background = (
        _color(background_attr, "page background")
        if background_attr is not None
        else style.background or (255, 255, 255)
    )

    _check_root_text(root)
    children: list[Node] = []
    for element in root:
        if element.tag in {"fonts", "style"}:
            continue
        children.append(
            _parse_element(
                element,
                style,
                rules,
                fonts,
                parent_path="page",
                inside_link=False,
            )
        )

    for child in children:
        if child.tag not in BLOCK_TAGS:
            raise DocumentError(
                f"<page> can only contain block elements, got <{child.tag}> at {child.path}"
            )

    page_root = Node(
        tag="page",
        attrs=dict(root.attrib),
        style=style,
        children=children,
        path="page",
    )
    _check_text_has_fonts(page_root, fonts)

    return Page(
        title=title,
        width=width,
        height=height,
        padding=padding,
        background=background,
        fonts=fonts,
        root=page_root,
    )


def _parse_fonts(root: ET.Element, base: Path) -> dict[str, Path]:
    fonts: dict[str, Path] = {}
    for container in root.findall("fonts"):
        if container.attrib:
            raise DocumentError("<fonts> does not take attributes")
        for element in container:
            if element.tag != "font":
                raise DocumentError(f"<fonts> can only contain <font>, got <{element.tag}>")
            _check_attrs(element, {"name", "src"}, "font")
            name = element.get("name", "").strip()
            src = element.get("src", "").strip()
            if not name:
                raise DocumentError("<font> needs a name")
            if not src:
                raise DocumentError(f"<font name='{name}'> needs a src")
            if name in fonts:
                raise DocumentError(f"duplicate font name '{name}'")
            path = Path(src)
            if not path.is_absolute():
                path = base / path
            path = path.resolve()
            if not path.is_file():
                raise DocumentError(f"font '{name}' not found: {path}")
            fonts[name] = path
    return fonts


def _parse_styles(root: ET.Element) -> list[Rule]:
    rules: list[Rule] = []
    for element in root.findall("style"):
        if element.attrib:
            raise DocumentError("<style> does not take attributes")
        if len(element):
            raise DocumentError("<style> can only contain CSS text")
        css = "".join(element.itertext())
        rules.extend(_parse_css(css))
    return rules


def _parse_element(
    element: ET.Element,
    parent_style: Style,
    rules: list[Rule],
    fonts: dict[str, Path],
    parent_path: str,
    inside_link: bool,
) -> Node:
    tag = element.tag
    if not isinstance(tag, str) or tag not in ALLOWED_TAGS:
        raise DocumentError(f"unknown element <{tag}> under {parent_path}")

    path = f"{parent_path}/{tag}"
    if element.get("id"):
        path += f"#{element.get('id')}"

    attrs = dict(element.attrib)
    allowed = {"class", "id"}
    if tag == "a":
        allowed.add("href")
    _check_attrs(element, allowed, tag, path)

    if tag == "a":
        if inside_link:
            raise DocumentError(f"nested <a> at {path}")
        href = _clean_href(attrs.get("href", ""), path)
        _check_href(href, path)
        attrs["href"] = href
        inside_link = True

    if tag == "br" and (len(element) or (element.text and element.text.strip())):
        raise DocumentError(f"<br> must be empty at {path}")

    style = _resolve_style(element, parent_style, rules, fonts)

    children: list[Node | Text] = []
    if element.text:
        children.append(Text(element.text))
    for child_element in element:
        child = _parse_element(
            child_element,
            style,
            rules,
            fonts,
            parent_path=path,
            inside_link=inside_link,
        )
        children.append(child)
        if child_element.tail:
            children.append(Text(child_element.tail))

    node = Node(tag=tag, attrs=attrs, style=style, children=children, path=path)
    _check_content_model(node)
    return node


def _check_content_model(node: Node) -> None:
    blocks = [c for c in node.children if isinstance(c, Node) and c.tag in BLOCK_TAGS]
    inlines = [
        c
        for c in node.children
        if (isinstance(c, Text) and c.value.strip())
        or (isinstance(c, Node) and c.tag in INLINE_TAGS)
    ]

    if blocks and inlines:
        raise DocumentError(f"mixed block and inline content in {node.path}")

    if node.tag in {"p", "h1", "h2", "h3", "span", "a"} and blocks:
        raise DocumentError(f"<{node.tag}> cannot contain block elements ({node.path})")


def _check_root_text(root: ET.Element) -> None:
    if root.text and root.text.strip():
        raise DocumentError("<page> cannot contain text; wrap it in <p>")
    for element in root:
        if element.tail and element.tail.strip():
            raise DocumentError("<page> cannot contain text; wrap it in <p>")


def _check_text_has_fonts(node: Node, fonts: dict[str, Path]) -> None:
    if node.style.font_family is not None and node.style.font_family not in fonts:
        raise DocumentError(
            f"unknown font family '{node.style.font_family}' at {node.path}"
        )
    for child in node.children:
        if isinstance(child, Text):
            if child.value.strip():
                if node.style.font_family is None:
                    raise DocumentError(f"text at {node.path} has no font-family")
        else:
            _check_text_has_fonts(child, fonts)


def _clean_href(href: str, path: str) -> str:
    # Browsers strip tab/newline/carriage return from URLs before parsing, so
    # "java\nscript:" would otherwise slip past the scheme check.
    href = href.replace("\t", "").replace("\n", "").replace("\r", "").strip()
    if not href:
        raise DocumentError(f"<a> needs an href at {path}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in href):
        raise DocumentError(f"control character in href at {path}")
    return href


def _check_href(href: str, path: str) -> None:
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https", "mailto"}:
        raise DocumentError(f"unsupported link scheme '{parsed.scheme}' at {path}")


# --------------------------------------------------------------------------
# Style parsing

_ALLOWED_PROPERTIES = {
    "font-family",
    "font-size",
    "color",
    "line-height",
    "text-align",
    "text-decoration",
    "background",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
}

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SELECTOR_RE = re.compile(
    r"^(?P<tag>[A-Za-z][\w-]*)?(?P<rest>(?:[.#][A-Za-z_][\w-]*)*)$"
)
_COMPOUND_RE = re.compile(r"([.#])([A-Za-z_][\w-]*)")


def _parse_css(css: str) -> list[Rule]:
    css = _COMMENT_RE.sub("", css)
    rules: list[Rule] = []
    position = 0
    for match in _RULE_RE.finditer(css):
        if css[position : match.start()].strip():
            raise DocumentError(f"cannot parse CSS near: {css[position:match.start()].strip()[:60]!r}")
        selector_text = match.group(1).strip()
        body = match.group(2)
        declarations = _parse_declarations(body, selector_text)
        for piece in selector_text.split(","):
            selector = _parse_selector(piece, selector_text)
            rules.append(
                Rule(selector=selector, declarations=declarations, order=len(rules))
            )
        position = match.end()
    if css[position:].strip():
        raise DocumentError(f"cannot parse CSS near: {css[position:].strip()[:60]!r}")
    return rules


def _parse_selector(text: str, context: str) -> Selector:
    text = text.strip()
    match = _SELECTOR_RE.fullmatch(text)
    if not match:
        raise DocumentError(f"unsupported selector '{text}' in '{context}'")

    tag = match.group("tag")
    rest = match.group("rest")
    if not tag and not rest:
        raise DocumentError(f"empty selector in '{context}'")

    classes: list[str] = []
    ids: list[str] = []
    for kind, name in _COMPOUND_RE.findall(rest):
        if kind == ".":
            classes.append(name)
        else:
            ids.append(name)

    if len(ids) > 1:
        raise DocumentError(f"only one id is supported per selector: '{text}'")

    return Selector(
        tag=tag.lower() if tag else None,
        classes=frozenset(classes),
        element_id=ids[0] if ids else None,
        specificity=(len(ids), len(classes), 1 if tag else 0),
    )


def _parse_declarations(body: str, selector: str) -> dict[str, object]:
    declarations: dict[str, object] = {}
    for raw in body.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        if ":" not in raw:
            raise DocumentError(f"expected 'property: value' in '{selector}': {raw!r}")
        name, value = (part.strip() for part in raw.split(":", 1))
        name = name.lower()

        if name in {"margin", "padding"}:
            for side, number in _edge_values(value, name, selector).items():
                declarations[f"{name}-{side}"] = number
            continue

        if name not in _ALLOWED_PROPERTIES:
            raise DocumentError(f"unsupported style property '{name}' in '{selector}'")

        if name == "font-family":
            family = value.strip("\"'")
            if not family:
                raise DocumentError(f"empty font-family in '{selector}'")
            declarations[name] = family
        elif name == "font-size":
            declarations[name] = _css_int(value, selector, minimum=1)
        elif name == "line-height":
            declarations[name] = _css_float(value, selector)
        elif name in {"color", "background"}:
            if name == "background" and value.lower() == "none":
                declarations[name] = None
            else:
                declarations[name] = _color(value, f"{name} in '{selector}'")
        elif name == "text-align":
            if value not in {"left", "center", "right"}:
                raise DocumentError(f"text-align must be left, center or right in '{selector}'")
            declarations[name] = value
        elif name == "text-decoration":
            if value not in {"underline", "none"}:
                raise DocumentError(f"text-decoration must be underline or none in '{selector}'")
            declarations[name] = value == "underline"
        else:
            declarations[name] = _css_int(value, selector, minimum=0)

    return declarations


def _edge_values(value: str, name: str, selector: str) -> dict[str, int]:
    parts = value.split()
    if not 1 <= len(parts) <= 4:
        raise DocumentError(f"{name} needs 1 to 4 values in '{selector}'")
    numbers = [_css_int(part, selector, minimum=0) for part in parts]
    if len(numbers) == 1:
        top = right = bottom = left = numbers[0]
    elif len(numbers) == 2:
        top, bottom = numbers
        right = left = numbers[1]
    elif len(numbers) == 3:
        top, right, bottom = numbers
        left = numbers[1]
    else:
        top, right, bottom, left = numbers
    return {"top": top, "right": right, "bottom": bottom, "left": left}


def _css_int(value: str, selector: str, minimum: int) -> int:
    if not re.fullmatch(r"\d+", value):
        raise DocumentError(f"expected an integer in '{selector}', got {value!r}")
    number = int(value)
    if number < minimum:
        raise DocumentError(f"value must be >= {minimum} in '{selector}'")
    return number


def _css_float(value: str, selector: str) -> float:
    if not re.fullmatch(r"\d+(?:\.\d+)?", value):
        raise DocumentError(f"expected a number in '{selector}', got {value!r}")
    number = float(value)
    if number <= 0:
        raise DocumentError(f"line-height must be > 0 in '{selector}'")
    return number


def _color(value: str, context: str) -> Color:
    try:
        rgb = ImageColor.getrgb(value)
    except ValueError as exc:
        raise DocumentError(f"bad color {value!r} for {context}") from exc
    if len(rgb) == 4:
        if rgb[3] != 255:
            raise DocumentError(f"transparent colors are not supported: {value!r}")
        rgb = rgb[:3]
    return cast(Color, tuple(rgb))


def _resolve_style(
    element: ET.Element,
    parent: Style,
    rules: list[Rule],
    fonts: dict[str, Path],
) -> Style:
    style = replace(parent, background=None, margin=Edges(), padding=Edges())
    matched = [rule for rule in rules if rule.selector.matches(element.tag, element.attrib)]
    matched.sort(key=lambda rule: (rule.selector.specificity, rule.order))

    for rule in matched:
        for name, value in rule.declarations.items():
            style = _apply_property(style, name, value)

    if style.font_family is not None and style.font_family not in fonts:
        raise DocumentError(
            f"unknown font family '{style.font_family}' on <{element.tag}>"
        )
    return style


def _apply_property(style: Style, name: str, value: object) -> Style:
    if name == "font-family":
        return replace(style, font_family=cast(str, value))
    if name == "font-size":
        return replace(style, font_size=cast(int, value))
    if name == "color":
        return replace(style, color=cast(Color, value))
    if name == "line-height":
        return replace(style, line_height=cast(float, value))
    if name == "text-align":
        return replace(style, align=cast(str, value))
    if name == "text-decoration":
        return replace(style, underline=cast(bool, value))
    if name == "background":
        return replace(style, background=cast(Color | None, value))
    if name.startswith("margin-"):
        return replace(
            style,
            margin=replace(style.margin, **{name.removeprefix("margin-"): cast(int, value)}),
        )
    if name.startswith("padding-"):
        return replace(
            style,
            padding=replace(style.padding, **{name.removeprefix("padding-"): cast(int, value)}),
        )
    raise AssertionError(f"unhandled property {name}")


# --------------------------------------------------------------------------
# Small helpers


def _check_attrs(
    element: ET.Element,
    allowed: set[str],
    tag: str,
    path: str | None = None,
) -> None:
    where = f" at {path}" if path else ""
    for name in element.attrib:
        if name not in allowed:
            raise DocumentError(f"unknown attribute '{name}' on <{tag}>{where}")


def _int_attr(
    element: ET.Element,
    name: str,
    *,
    required: bool,
    minimum: int,
) -> int | None:
    raw = element.get(name)
    if raw is None:
        if required:
            raise DocumentError(f"<{element.tag}> needs a {name} attribute")
        return None
    if not re.fullmatch(r"\d+", raw.strip()):
        raise DocumentError(f"<{element.tag}> {name} must be an integer, got {raw!r}")
    number = int(raw)
    if number < minimum:
        raise DocumentError(f"<{element.tag}> {name} must be >= {minimum}")
    return number
