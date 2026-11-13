"""Markdown heading handling: mask headings, locate sections."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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


def has_headings(text: str) -> bool:
    return _HEADING.search(text) is not None


_BLANK = re.compile(r"\n[ \t]*\n")


def paragraph_ranges(text: str) -> list[tuple[int, int]]:
    """Character ranges of blank-line delimited blocks, derived before markdown parsing."""
    ranges, start = [], 0

    for m in _BLANK.finditer(text):
        ranges.append((start, m.start()))
        start = m.end()

    ranges.append((start, len(text)))

    return ranges


_BLOCK_START = re.compile(r"\s*(?:>|[-*+][ \t]|\d+[.)][ \t])")


def prose_paragraphs(text: str) -> list[tuple[int, int]]:
    """Paragraph ranges holding running prose: heading lines trimmed, lists and quotes skipped."""
    out = []

    for start, end in paragraph_ranges(text):
        while text.startswith("#", start) or text[start:end].lstrip().startswith("#"):
            newline = text.find("\n", start, end)

            if newline < 0:
                start = end

                break

            start = newline + 1

        block = text[start:end]

        if block.strip() and not _BLOCK_START.match(block):
            out.append((start, end))

    return out


_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)[^`\n]+?\1")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>\n]*>")
_LINK = re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)")
_URL = re.compile(r"https?://[^\s)>\]]+")
_LIST_MARKER = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])(?=[ \t])", re.MULTILINE)
_EMPHASIS = re.compile(r"\*\*|__")


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def mask_code_blocks(text: str) -> str:
    """Blank fenced code and table rows with spaces, keeping offsets and newlines."""
    out, fence = [], None

    for line in text.splitlines(keepends=True):
        m = _FENCE.match(line)
        stripped = line.strip()
        table = stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1

        if fence is None and m:
            fence = m.group(1)[0] * 3
            out.append(re.sub(r"[^\n]", " ", line))
        elif fence is not None:
            closes = m is not None and m.group(1).startswith(fence)
            out.append(re.sub(r"[^\n]", " ", line))
            fence = None if closes else fence
        elif table:
            out.append(re.sub(r"[^\n]", " ", line))
        else:
            out.append(line)

    return "".join(out)


def mask_markup(text: str) -> str:
    """Everything that is markup rather than prose, blanked in place.

    Fenced code, tables, inline code, HTML, link targets, bare URLs, list markers, emphasis
    marks and headings. Link text stays.
    """
    out = mask_code_blocks(text)
    out = _HTML_COMMENT.sub(_blank, out)
    out = _INLINE_CODE.sub(_blank, out)
    out = _HTML_TAG.sub(_blank, out)
    out = _LINK.sub(lambda m: " " + m.group(1) + " " * (len(m.group(0)) - len(m.group(1)) - 1), out)
    out = _URL.sub(_blank, out)
    out = _LIST_MARKER.sub(lambda m: m.group(1) + " ", out)
    out = _EMPHASIS.sub("  ", out)

    return mask_headings(out)


# ---- structure model -------------------------------------------------------------------------

_ATX = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t#]*$")
_ITEM = re.compile(r"^([ \t]*)([-*+]|\d+[.)])[ \t]+(.*)$")
_MD_LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\n]*)\)")
_BARE_URL = re.compile(r"https?://[^\s)>\]]+")


@dataclass
class Heading:
    level: int
    line: int
    start: int
    end: int
    title: str


@dataclass
class ListItem:
    start: int
    end: int
    line: int


@dataclass
class ListBlock:
    line: int
    ordered: bool
    items: list[ListItem] = field(default_factory=list)


@dataclass
class Fence:
    start: int
    end: int
    line: int
    lang: str


@dataclass
class Link:
    start: int
    line: int
    url: str


@dataclass
class Model:
    """What the markdown holds beyond prose: heading levels, lists, code and links."""

    headings: list[Heading] = field(default_factory=list)
    lists: list[ListBlock] = field(default_factory=list)
    fences: list[Fence] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    inline_code_chars: int = 0
    length: int = 0


def parse(text: str) -> Model:
    """A line-based pass over raw markdown. Offsets are character offsets into text."""
    model = Model(length=len(text))
    offset, fence_start, fence_line, fence_lang, fence_mark = 0, 0, 0, "", ""
    block: ListBlock | None = None

    for number, raw in enumerate(text.splitlines(keepends=True), start=1):
        line = raw.rstrip("\r\n")
        fenced = _FENCE.match(line)
        start, end = offset, offset + len(line)
        offset += len(raw)

        if fence_mark:
            if fenced and fenced.group(1).startswith(fence_mark):
                model.fences.append(Fence(fence_start, end, fence_line, fence_lang))
                fence_mark = ""

            continue

        if fenced:
            fence_mark = fenced.group(1)[0] * 3
            fence_start, fence_line = start, number
            fence_lang = line.strip()[len(fenced.group(1)) :].strip()
            block = None

            continue

        heading = _ATX.match(line)
        item = _ITEM.match(line)

        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            model.headings.append(Heading(level, number, start, end, title))
            block = None
        elif item:
            if block is None:
                block = ListBlock(number, item.group(2)[0].isdigit())
                model.lists.append(block)

            block.items.append(ListItem(start + item.start(3), end, number))
        elif not line.strip() or not line.startswith((" ", "\t")):
            block = None
        elif block is not None and block.items:
            block.items[-1].end = end

        model.inline_code_chars += sum(len(m.group(0)) for m in _INLINE_CODE.finditer(line))

        for m in _MD_LINK.finditer(line):
            model.links.append(Link(start + m.start(), number, m.group(2)))

        stripped = _MD_LINK.sub("", line)
        model.links.extend(Link(start, number, m.group(0)) for m in _BARE_URL.finditer(stripped))

    if fence_mark:
        model.fences.append(Fence(fence_start, len(text), fence_line, fence_lang))

    return model
