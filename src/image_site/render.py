from __future__ import annotations

from PIL import Image, ImageDraw

from .fonts import FontBook
from .layout import Layout, Rect, TextOp


def render(layout: Layout, fonts: FontBook) -> Image.Image:
    image = Image.new(
        "RGB",
        (layout.width, layout.height),
        layout.background,
    )
    draw = ImageDraw.Draw(image)

    for op in layout.ops:
        if isinstance(op, Rect):
            if op.right <= op.left or op.bottom <= op.top:
                continue
            draw.rectangle(
                [op.left, op.top, op.right - 1, op.bottom - 1],
                fill=op.color,
            )
            continue

        font = fonts.get(op.font_family, op.font_size)
        draw.text(
            (op.x, op.baseline),
            op.text,
            font=font,
            fill=op.color,
            anchor="ls",
        )
        if op.underline:
            underline_width = round(fonts.length(op.font_family, op.font_size, op.text))
            if underline_width > 0:
                y = op.baseline + 2
                draw.rectangle(
                    [op.x, y, op.x + underline_width - 1, y],
                    fill=op.color,
                )

    return image
