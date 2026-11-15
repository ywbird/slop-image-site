from __future__ import annotations

from pathlib import Path

from PIL import ImageFont


class FontBook:
    """Loads and caches fonts declared in the XML document."""

    def __init__(self, fonts: dict[str, Path]):
        self._paths = fonts
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, family: str, size: int) -> ImageFont.FreeTypeFont:
        key = (family, size)
        if key not in self._cache:
            try:
                path = self._paths[family]
            except KeyError as exc:
                raise ValueError(f"unknown font family '{family}'") from exc
            self._cache[key] = ImageFont.truetype(str(path), size)
        return self._cache[key]

    def length(self, family: str, size: int, text: str) -> float:
        return self.get(family, size).getlength(text)

    def metrics(self, family: str, size: int) -> tuple[int, int]:
        return self.get(family, size).getmetrics()
