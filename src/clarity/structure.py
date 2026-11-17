"""Document structure as the caller gives it: a tree of sections. Nothing is inferred from text.

A section has an optional id, title, subtitle, text (paragraphs split on blank lines), items (a
bulleted list, one sentence unit per item) and child sections. A plain string is one section
whose text is the string. The tree is rendered into one string for a single spaCy parse: blocks
in tree order (title, subtitle, text, items, then the child sections), joined by a blank line.
Every block starts a sentence, so a title or item without a full stop never runs into the next.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from spacy.language import Language
from spacy.tokens import Doc

SECTION_KEYS = ("id", "title", "subtitle", "text", "items", "sections")
FRAGMENT_FIELDS = ("title", "subtitle")
TREE_SUFFIXES = (".json", ".yml", ".yaml")
JOIN = "\n\n"
_BLANK = re.compile(r"\n[ \t]*\n")


class StructureError(ValueError):
    """Raised for a malformed document tree."""


@dataclass
class Block:
    """One unit of a section: its title, its subtitle, one paragraph of its text, or one item."""

    start: int
    end: int
    field: str  # title, subtitle, text or items[i]
    field_start: int  # offset of the whole field in the rendered text
    part: int


@dataclass
class Part:
    index: int
    path: str
    depth: int
    parent: int | None
    id: str | None = None
    title: str | None = None
    children: list[int] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    @property
    def body(self) -> list[Block]:
        """Text paragraphs and items: everything but the title and subtitle."""
        return [b for b in self.blocks if b.field not in FRAGMENT_FIELDS]


@dataclass
class Structure:
    text: str
    parts: list[Part]
    tree: bool = False

    @property
    def blocks(self) -> list[Block]:
        return [b for p in self.parts for b in p.blocks]

    @property
    def title(self) -> str | None:
        """The document title: the root part's title, else the first part title."""
        return self.parts[0].title or next((p.title for p in self.parts if p.title), None)

    def headings(self) -> list[tuple[int, int, int, str]]:
        """(level, start, end, title) of every part title; level is the part's depth plus one."""
        return [(p.depth + 1, b.start, b.end, p.title or "")
                for p in self.parts for b in p.blocks if b.field == "title"]  # fmt: skip

    def sections(self) -> list[tuple[int, int]]:
        """One range per section with a body: from its first body block to its last."""
        return [(p.body[0].start, p.body[-1].end) for p in self.parts if p.body]

    def paragraphs(self) -> list[tuple[int, int]]:
        """Prose paragraphs: the blocks of every part's text field."""
        return [(b.start, b.end) for b in self.blocks if b.field == "text"]

    def body_blocks(self) -> list[tuple[int, int]]:
        """Every block that is not a title or subtitle: paragraphs and items."""
        return [(b.start, b.end) for p in self.parts for b in p.body]

    def item_lists(self) -> list[list[Block]]:
        """Each part's items, as one list per part that has them."""
        out = [[b for b in p.blocks if b.field.startswith("items")] for p in self.parts]

        return [x for x in out if x]

    def block_at(self, offset: int) -> Block | None:
        for b in self.blocks:
            if b.start <= offset < b.end or (b.start == b.end == offset):
                return b

        return None

    def part_at(self, offset: int) -> int:
        """The part owning a character offset; offsets between blocks go to the next block."""
        found = self.block_at(offset)

        if found is not None:
            return found.part

        later = [b for b in self.blocks if b.start >= offset]

        return later[0].part if later else (self.blocks[-1].part if self.blocks else 0)

    def field_kind(self, offset: int) -> str:
        """title, subtitle, text or items for the field holding an offset; text between blocks."""
        b = self.block_at(offset)

        return b.field.split("[")[0] if b is not None else "text"

    def clip(self, start: int, end: int) -> tuple[int, int]:
        """A span cut back to the field it starts in, so its offsets stay inside that field and a
        finding never crosses into another field or section."""
        first = self.block_at(start)

        if first is None:
            return start, end

        same = [b.end for b in self.parts[first.part].blocks if b.field == first.field]

        return start, min(end, max(same))

    def locate(self, start: int, end: int) -> dict[str, Any]:
        """A span as the caller sees it: field, offsets and line/col inside that field."""
        b = self.block_at(start)

        if b is None:
            return {"field": "text", "span": {"start": start, "end": end}, "line": 1, "col": 1}

        base = b.field_start
        line = self.text.count("\n", base, start) + 1
        col = start - max(self.text.rfind("\n", base, start) + 1, base) + 1

        return {"field": b.field, "span": {"start": start - base, "end": end - base},
                "line": line, "col": col}  # fmt: skip

    def words(self, doc: Doc, part: int) -> int:
        """Words in one part's own blocks (not its children)."""
        total = 0

        for b in self.parts[part].blocks:
            span = doc.char_span(b.start, b.end, alignment_mode="expand")
            total += sum(1 for t in span or [] if not t.is_punct and not t.is_space)

        return total

    def descendants(self, part: int) -> list[int]:
        out = [part]

        for child in self.parts[part].children:
            out += self.descendants(child)

        return out


def _paragraph_blocks(text: str, base: int, field_name: str, part: int) -> list[Block]:
    out, start = [], 0

    for m in [*_BLANK.finditer(text), None]:
        end = m.start() if m else len(text)
        piece = text[start:end]

        if piece.strip():
            lead = len(piece) - len(piece.lstrip())
            trail = len(piece) - len(piece.rstrip())
            out.append(Block(base + start + lead, base + end - trail, field_name, base, part))

        start = m.end() if m else start

    return out


def from_text(text: str) -> Structure:
    """A plain string: one part whose text is the string, with its offsets unchanged."""
    root = Part(0, "", 0, None)
    root.blocks = _paragraph_blocks(text, 0, "text", 0)

    return Structure(text, [root], tree=False)


def _check(node: Any, path: str) -> dict[str, Any]:
    where = f"section {path or '(root)'}"

    if not isinstance(node, dict):
        raise StructureError(f"{where}: expected a mapping with {', '.join(SECTION_KEYS)}")

    unknown = sorted(set(node) - set(SECTION_KEYS))

    if unknown:
        raise StructureError(
            f"{where}: unknown keys {unknown}; a section has {', '.join(SECTION_KEYS)}"
        )

    for key in ("id", "title", "subtitle", "text"):
        if node.get(key) is not None and not isinstance(node[key], str):
            raise StructureError(f"{where}: {key} must be a string")

    items = node.get("items")

    if items is not None and (not isinstance(items, list)
                              or not all(isinstance(i, str) for i in items)):  # fmt: skip
        raise StructureError(f"{where}: items must be a list of strings")

    if node.get("sections") is not None and not isinstance(node["sections"], list):
        raise StructureError(f"{where}: sections must be a list")

    return node


def from_tree(tree: Any) -> Structure:
    """A document tree rendered into one string, with every block's place recorded."""
    pieces: list[str] = []
    parts: list[Part] = []
    offset = 0

    def put(value: str, field_name: str, part: int, split: bool) -> None:
        nonlocal offset

        if pieces:
            pieces.append(JOIN)
            offset += len(JOIN)

        blocks = (_paragraph_blocks(value, offset, field_name, part) if split
                  else [Block(offset, offset + len(value), field_name, offset, part)])  # fmt: skip
        parts[part].blocks += [b for b in blocks if b.end > b.start]
        pieces.append(value)
        offset += len(value)

    def walk(node: Any, path: str, depth: int, parent: int | None) -> None:
        node = _check(node, path)
        index = len(parts)
        parts.append(Part(index, path, depth, parent, node.get("id"), node.get("title")))

        if parent is not None:
            parts[parent].children.append(index)

        if node.get("title"):
            put(node["title"], "title", index, False)

        if node.get("subtitle"):
            put(node["subtitle"], "subtitle", index, False)

        if node.get("text"):
            put(node["text"], "text", index, True)

        for i, item in enumerate(node.get("items") or []):
            if item.strip():
                put(item, f"items[{i}]", index, False)

        for i, child in enumerate(node.get("sections") or []):
            walk(child, f"{path}.{i}" if path else str(i), depth + 1, index)

    walk(tree, "", 0, None)

    return Structure("".join(pieces), parts, tree=True)


def coerce(value: str | dict[str, Any] | Structure) -> Structure:
    """A Structure from a plain string, a tree mapping, or a Structure."""
    if isinstance(value, Structure):
        return value

    if isinstance(value, dict):
        return from_tree(value)

    return from_text(value)


def load(path: Path) -> Structure:
    """Read a file: a .json/.yml/.yaml file is a tree, anything else is plain text."""
    raw = path.read_text(encoding="utf-8")

    if path.suffix.lower() not in TREE_SUFFIXES:
        return from_text(raw)

    try:
        tree = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise StructureError(f"{path}: not a valid document tree: {exc}") from exc

    return from_tree(tree)


def parse_doc(nlp: Language, s: Structure) -> Doc:
    """One spaCy parse of the rendered text, with a sentence starting at every block. The parser
    may not split a title or subtitle, so each is one sentence."""
    doc = nlp.make_doc(s.text)
    starts = {b.start for b in s.blocks}
    heads = {b.start: b.end for b in s.blocks if b.field in ("title", "subtitle")}
    inside = False
    head_end = 0

    for tok in doc:
        if tok.idx in starts and tok.i > 0:
            tok.is_sent_start = True

        if tok.idx in heads:
            inside, head_end = True, heads[tok.idx]
        elif inside and tok.idx >= head_end:
            inside = False
        elif inside:
            tok.is_sent_start = False

    for _, proc in nlp.pipeline:
        doc = proc(doc)

    return doc


_FINDING = {
    "type": "object",
    "properties": {
        "rule": {"type": "string"},
        "category": {"type": "string"},
        "severity": {"enum": ["info", "warning", "error"]},
        "confidence": {"enum": ["exact", "inferred"]},
        "message": {"type": "string"},
        "section": {"type": "string", "description": "path of the section the finding is in"},
        "field": {"type": "string", "description": "title, subtitle, text or items[i]"},
        "span": {"type": "object", "properties": {"start": {"type": "integer"},
                 "end": {"type": "integer"}, "text": {"type": "string"}},
                 "description": "character offsets inside the field"},
        "line": {"type": "integer", "description": "line inside the field, from 1"},
        "col": {"type": "integer", "description": "column inside the line, from 1"},
        "over_allowance": {"type": "boolean"},
        "experimental": {"type": "boolean", "description": "reported, not scored"},
        "detail": {"type": "string"},
        "children": {"type": "array", "description": "member findings of a composite rule"},
    },
}

SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$defs": {
        "section": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "description": "your label, returned unchanged"},
                "title": {"type": "string"},
                "subtitle": {"type": "string"},
                "text": {"type": "string", "description": "prose; blank lines separate paragraphs"},
                "items": {"type": "array", "items": {"type": "string"},
                          "description": "a list, one string per item, without bullets"},
                "sections": {"type": "array", "items": {"$ref": "#/$defs/section"}},
            },
        },
        "result_section": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "id": {"type": "string"},
                "title": {"type": "string"},
                "words": {"type": "integer"},
                "score": {"type": "number", "description": "this section's own fields"},
                "rollup": {"type": "object", "properties": {"score": {"type": "number"},
                           "words": {"type": "integer"}},
                           "description": "this section and every section under it"},
                "findings": {"type": "array", "items": _FINDING},
                "categories": {"type": "array"},
                "sections": {"type": "array", "items": {"$ref": "#/$defs/result_section"}},
            },
        },
    },
    "input": {"$ref": "#/$defs/section"},
    "response": {
        "type": "object",
        "properties": {
            "score": {"type": "number", "description": "the root section's rollup score"},
            "words": {"type": "integer"},
            "sentences": {"type": "integer"},
            "section": {"$ref": "#/$defs/result_section"},
            "readability": {"type": "object"},
            "prose_metrics": {"type": "object"},
            "disabled_rules": {"type": "array"},
        },
    },
}
