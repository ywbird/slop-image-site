from __future__ import annotations

from dataclasses import dataclass
import re

from .document import BLOCK_TAGS, Color, DocumentError, Node, Page, Style, Text
from .fonts import FontBook


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int
    color: Color


@dataclass(frozen=True)
class TextOp:
    x: int
    baseline: int
    text: str
    font_family: str
    font_size: int
    color: Color
    underline: bool


@dataclass(frozen=True)
class Link:
    href: str
    label: str
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class Layout:
    width: int
    height: int
    background: Color
    ops: list[Rect | TextOp]
    links: list[Link]


@dataclass
class _LinkInfo:
    href: str
    label: str = ""


@dataclass(frozen=True)
class _Piece:
    kind: str
    text: str
    style: Style
    link: _LinkInfo | None


@dataclass
class _Token:
    text: str
    width: float
    style: Style
    link: _LinkInfo | None
    space: bool = False
    br: bool = False
    x: float = 0.0


def layout_page(page: Page, fonts: FontBook) -> Layout:
    ops: list[Rect | TextOp] = []
    links: list[Link] = []

    content_width = page.width - page.padding * 2
    if content_width <= 0:
        raise DocumentError("page padding leaves no room for content")

    cursor = page.padding
    for child in page.root.children:
        assert isinstance(child, Node)
        cursor += child.style.margin.top
        width = content_width - child.style.margin.left - child.style.margin.right
        if width <= 0:
            raise DocumentError(f"no width left for {child.path}")
        height = _layout_block(
            child,
            x=page.padding + child.style.margin.left,
            y=cursor,
            width=width,
            fonts=fonts,
            ops=ops,
            links=links,
        )
        cursor += height + child.style.margin.bottom

    height = cursor + page.padding
    if page.height is not None:
        if height > page.height:
            raise DocumentError(
                f"content needs {height}px of height, but the page is {page.height}px"
            )
        height = page.height

    return Layout(
        width=page.width,
        height=height,
        background=page.background,
        ops=ops,
        links=links,
    )


def _layout_block(
    node: Node,
    x: int,
    y: int,
    width: int,
    fonts: FontBook,
    ops: list[Rect | TextOp],
    links: list[Link],
) -> int:
    style = node.style
    padding = style.padding
    content_width = width - padding.left - padding.right
    if content_width <= 0:
        raise DocumentError(f"no content width left for {node.path}")

    content_x = x + padding.left
    content_y = y + padding.top
    start = len(ops)

    if _has_block_children(node):
        cursor = content_y
        for child in node.children:
            if isinstance(child, Text):
                continue
            assert isinstance(child, Node)
            cursor += child.style.margin.top
            child_width = content_width - child.style.margin.left - child.style.margin.right
            if child_width <= 0:
                raise DocumentError(f"no width left for {child.path}")
            cursor += _layout_block(
                child,
                x=content_x + child.style.margin.left,
                y=cursor,
                width=child_width,
                fonts=fonts,
                ops=ops,
                links=links,
            )
            cursor += child.style.margin.bottom
        content_height = cursor - content_y
    else:
        pieces: list[_Piece] = []
        _flatten(node, None, pieces)
        content_height = _layout_inline(
            pieces,
            x=content_x,
            y=content_y,
            width=content_width,
            block_style=style,
            fonts=fonts,
            ops=ops,
            links=links,
        )

    height = padding.top + content_height + padding.bottom
    if style.background is not None:
        ops.insert(start, Rect(x, y, x + width, y + height, style.background))
    return height


def _has_block_children(node: Node) -> bool:
    return any(
        isinstance(child, Node) and child.tag in BLOCK_TAGS for child in node.children
    )


def _flatten(node: Node, link: _LinkInfo | None, out: list[_Piece]) -> None:
    for child in node.children:
        if isinstance(child, Text):
            out.append(_Piece("text", child.value, node.style, link))
            if link is not None:
                link.label += child.value
        elif child.tag == "br":
            out.append(_Piece("br", "", child.style, None))
        elif child.tag == "a":
            _flatten(child, _LinkInfo(child.attrs["href"]), out)
        else:
            _flatten(child, link, out)


def _layout_inline(
    pieces: list[_Piece],
    x: int,
    y: int,
    width: int,
    block_style: Style,
    fonts: FontBook,
    ops: list[Rect | TextOp],
    links: list[Link],
) -> int:
    if width <= 0:
        raise DocumentError("inline content has no width")

    tokens = _tokenize(pieces, fonts)
    line: list[_Token] = []
    line_width = 0.0
    cursor = y

    for token in tokens:
        if token.br:
            cursor += _flush_line(
                line, x, cursor, width, block_style.align, block_style, fonts, ops, links
            )
            line = []
            line_width = 0.0
            continue

        if token.space:
            if not line:
                continue
            token.x = line_width
            line.append(token)
            line_width += token.width
            continue

        if line and line_width + token.width > width:
            cursor += _flush_line(
                line, x, cursor, width, block_style.align, block_style, fonts, ops, links
            )
            line = []
            line_width = 0.0

        if not line and token.width > width:
            for chunk in _split_long_token(token, width, fonts):
                if line and line_width + chunk.width > width:
                    cursor += _flush_line(
                        line,
                        x,
                        cursor,
                        width,
                        block_style.align,
                        block_style,
                        fonts,
                        ops,
                        links,
                    )
                    line = []
                    line_width = 0.0
                chunk.x = line_width
                line.append(chunk)
                line_width += chunk.width
                if line_width >= width:
                    cursor += _flush_line(
                        line,
                        x,
                        cursor,
                        width,
                        block_style.align,
                        block_style,
                        fonts,
                        ops,
                        links,
                    )
                    line = []
                    line_width = 0.0
            continue

        token.x = line_width
        line.append(token)
        line_width += token.width

    if line:
        cursor += _flush_line(
            line, x, cursor, width, block_style.align, block_style, fonts, ops, links
        )

    return cursor - y


def _tokenize(pieces: list[_Piece], fonts: FontBook) -> list[_Token]:
    tokens: list[_Token] = []
    last_space = False

    for piece in pieces:
        if piece.kind == "br":
            tokens.append(_Token("", 0.0, piece.style, None, br=True))
            last_space = False
            continue

        for match in re.finditer(r"\s+|\S+", piece.text):
            text = match.group(0)
            if text.isspace():
                if last_space:
                    continue
                family = piece.style.font_family
                space_width = (
                    fonts.length(family, piece.style.font_size, " ") if family else 0.0
                )
                tokens.append(
                    _Token(" ", space_width, piece.style, piece.link, space=True)
                )
                last_space = True
            else:
                family = piece.style.font_family
                assert family is not None
                width = fonts.length(family, piece.style.font_size, text)
                tokens.append(_Token(text, width, piece.style, piece.link))
                last_space = False

    return tokens


def _split_long_token(token: _Token, width: int, fonts: FontBook) -> list[_Token]:
    style = token.style
    family = style.font_family
    assert family is not None

    chunks: list[_Token] = []
    current = ""
    for character in token.text:
        candidate = current + character
        if current and fonts.length(family, style.font_size, candidate) > width:
            chunks.append(
                _Token(
                    current,
                    fonts.length(family, style.font_size, current),
                    style,
                    token.link,
                )
            )
            current = character
        else:
            current = candidate
    if current:
        chunks.append(
            _Token(current, fonts.length(family, style.font_size, current), style, token.link)
        )
    return chunks


def _flush_line(
    tokens: list[_Token],
    x: int,
    line_top: int,
    content_width: int,
    align: str,
    block_style: Style,
    fonts: FontBook,
    ops: list[Rect | TextOp],
    links: list[Link],
) -> int:
    while tokens and tokens[-1].space:
        tokens.pop()

    if not tokens:
        return max(1, round(block_style.line_height * block_style.font_size))

    line_height = 0.0
    ascent = 0
    descent = 0
    has_text = False

    for token in tokens:
        if token.space:
            continue
        family = token.style.font_family
        if family is None:
            continue
        line_height = max(line_height, token.style.line_height * token.style.font_size)
        token_ascent, token_descent = fonts.metrics(family, token.style.font_size)
        ascent = max(ascent, token_ascent)
        descent = max(descent, token_descent)
        has_text = True

    if not has_text:
        line_height = block_style.line_height * block_style.font_size
        ascent = max(1, round(line_height * 0.8))
        descent = max(0, round(line_height) - ascent)

    line_height_px = max(1, round(line_height), ascent + descent)
    half_leading = max(0, (line_height_px - ascent - descent) / 2)
    baseline = line_top + round(half_leading) + ascent

    line_width = tokens[-1].x + tokens[-1].width
    if align == "center":
        offset = max(0, round((content_width - line_width) / 2))
    elif align == "right":
        offset = max(0, round(content_width - line_width))
    else:
        offset = 0

    _draw_runs(tokens, x + offset, baseline, ops)
    _collect_links(tokens, x + offset, line_top, line_height_px, links)

    return line_height_px


def _draw_runs(tokens: list[_Token], x: int, baseline: int, ops: list[Rect | TextOp]) -> None:
    run_text = ""
    run_left = 0.0
    run_key: tuple[str, int, Color, bool] | None = None

    def flush() -> None:
        if run_key is None or not run_text:
            return
        family, size, color, underline = run_key
        ops.append(
            TextOp(
                x=round(run_left),
                baseline=baseline,
                text=run_text,
                font_family=family,
                font_size=size,
                color=color,
                underline=underline,
            )
        )

    for token in tokens:
        family = token.style.font_family
        if family is None:
            continue
        key = (
            family,
            token.style.font_size,
            token.style.color,
            token.style.underline,
        )
        if key != run_key:
            flush()
            run_key = key
            run_left = x + token.x
            run_text = ""
        run_text += token.text

    flush()


def _collect_links(
    tokens: list[_Token],
    x: int,
    line_top: int,
    line_height: int,
    links: list[Link],
) -> None:
    current: _LinkInfo | None = None
    start = 0.0
    end = 0.0

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        links.append(
            Link(
                href=current.href,
                label=" ".join(current.label.split()),
                left=max(0, round(start) - 2),
                top=line_top,
                right=round(end) + 2,
                bottom=line_top + line_height,
            )
        )
        current = None

    for token in tokens:
        if token.link is None:
            flush()
            continue
        if current is not token.link:
            flush()
            current = token.link
            start = x + token.x
        end = x + token.x + token.width

    flush()
