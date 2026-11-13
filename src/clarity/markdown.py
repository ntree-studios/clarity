"""Markdown heading handling: mask headings, locate sections."""

from __future__ import annotations

import re

_HEADING = re.compile(r"^(#{1,6})[ \t]+.*$", re.MULTILINE)


def mask_headings(text: str) -> str:
    """Blank heading lines with spaces so character offsets are preserved."""
    return _HEADING.sub(lambda m: " " * len(m.group(0)), text)


def section_ranges(text: str) -> list[tuple[int, int]]:
    """Character ranges of each section. A document without headings is one section."""
    starts = [m.end() for m in _HEADING.finditer(text)]
    heads = [m.start() for m in _HEADING.finditer(text)]

    if not starts:
        return [(0, len(text))]

    ranges = []

    if heads[0] > 0 and text[: heads[0]].strip():
        ranges.append((0, heads[0]))

    for i, start in enumerate(starts):
        end = heads[i + 1] if i + 1 < len(heads) else len(text)
        ranges.append((start, end))

    return ranges
