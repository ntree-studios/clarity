"""A planted test set for the off-topic rules, built from hand-written topic pools.

Each pool in tests/topics/pools/ is a title and paragraphs on one subject. The builder makes, per
pool: an on-topic document, one with an unrelated paragraph inserted, one with a digression that
returns, one that drifts to another subject at the end, one with a section heading that does not
match its body, and one with a paragraph whose second half wanders to another subject. Each case
is a section tree and names the rule expected to fire and the lines it should fire on, counted
in the tree's rendered text (title, a blank line, then each block).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clarity.structure import Structure, from_tree

POOLS = Path(__file__).parent / "topics" / "pools"
SUBJECTS = ("espresso", "sourdough", "gardening", "insulation")
HEADINGS = {
    "espresso": ("Grind and dose", "Water and timing", "Milk and cleaning"),
    "sourdough": ("The starter", "Mixing and rising", "Baking the loaf"),
    "gardening": ("Starting the plants", "Soil and water", "Support and harvest"),
    "insulation": ("The attic", "Walls and windows", "Pipes and upkeep"),
}
WRONG_HEADING = "Comparing mortgage rates from banks"
OFF_TOPIC_RULES = (
    "topic-drift", "topic-digression", "off-topic-share", "orphan-paragraph",
    "section-heading-mismatch", "wandering-paragraph",
)  # fmt: skip


@dataclass
class Case:
    name: str
    tree: dict[str, Any]
    # rule id -> (first line, last line) where it should fire; empty for an on-topic document
    expect: dict[str, tuple[int, int]] = field(default_factory=dict)


def pool(name: str) -> tuple[str, list[str]]:
    blocks = [b.strip() for b in (POOLS / f"{name}.txt").read_text().split("\n\n") if b.strip()]

    return blocks[0].lstrip("# "), blocks[1:]


class Doc:
    """Builds a section tree block by block and remembers the rendered lines of marked blocks.

    A block "## Heading" starts a child section; other blocks are paragraphs of the current one.
    """

    def __init__(self, title: str) -> None:
        self.title = title
        self.blocks = [title]
        self.marks: dict[str, list[int]] = {}

    def line(self) -> int:
        return sum(b.count("\n") + 2 for b in self.blocks) + 1

    def add(self, blocks: list[str], mark: str | None = None) -> None:
        for block in blocks:
            if mark:
                start = self.line()
                self.marks.setdefault(mark, []).extend([start, start + block.count("\n")])

            self.blocks.append(block)

    def span(self, mark: str) -> tuple[int, int]:
        return min(self.marks[mark]), max(self.marks[mark])

    def tree(self) -> dict[str, Any]:
        root: dict[str, Any] = {"title": self.title}
        current: dict[str, Any] = root
        paragraphs: list[str] = []

        def flush() -> None:
            if paragraphs:
                current["text"] = "\n\n".join(paragraphs)
                paragraphs.clear()

        for block in self.blocks[1:]:
            if block.startswith("## "):
                flush()
                current = {"title": block[3:]}
                root.setdefault("sections", []).append(current)
            else:
                paragraphs.append(block)

        flush()

        return root


def _sentences(paragraph: str) -> list[str]:
    import re

    return [s for s in re.split(r"(?<=[.!?])\s+", paragraph) if s]


def build() -> list[Case]:
    _, cycling = pool("cycling")
    _, mortgage = pool("mortgage")
    cases = []

    for subject in SUBJECTS:
        title, paras = pool(subject)
        heads = HEADINGS[subject]

        doc = Doc(title)
        doc.add(paras)
        cases.append(Case(f"{subject}/on-topic", doc.tree()))

        doc = Doc(title)
        doc.add(paras[:6])
        doc.add(cycling[:1], "x")
        doc.add(paras[6:])
        cases.append(Case(f"{subject}/inserted", doc.tree(), {"orphan-paragraph": doc.span("x")}))

        doc = Doc(title)
        doc.add(paras[:6])
        doc.add(cycling, "x")
        doc.add(paras[6:])
        cases.append(Case(f"{subject}/digression", doc.tree(),
                          {"topic-digression": doc.span("x")}))  # fmt: skip

        doc = Doc(title)
        doc.add(paras[:8])
        doc.add(mortgage[:6], "x")
        cases.append(Case(f"{subject}/drift", doc.tree(), {
            "topic-drift": doc.span("x"), "off-topic-share": (1, doc.line()),
        }))  # fmt: skip

        doc = Doc(title)
        doc.add([f"## {heads[0]}"])
        doc.add(paras[:4])
        doc.add([f"## {WRONG_HEADING}"], "x")  # a title is one line, as "## " was
        doc.add(paras[4:8], "x")
        doc.add([f"## {heads[2]}"])
        doc.add(paras[8:])
        cases.append(Case(f"{subject}/heading", doc.tree(),
                          {"section-heading-mismatch": doc.span("x")}))  # fmt: skip

        doc = Doc(title)
        doc.add(paras[:5])
        mixed = " ".join(_sentences(paras[5]) + _sentences(mortgage[3]))
        doc.add([mixed], "x")
        doc.add(paras[6:])
        cases.append(Case(f"{subject}/wandering", doc.tree(),
                          {"wandering-paragraph": doc.span("x")}))  # fmt: skip

    return cases


def score(cases: list[Case], findings_of: Any) -> dict[str, dict[str, int]]:
    """Per rule: planted cases, found, missed and false alarms.

    findings_of(tree) returns findings. A finding is found when its rule has an expectation in the
    case and its line falls in the expected range; any other finding of an off-topic rule is a
    false alarm.
    """
    table = {r: {"planted": 0, "found": 0, "missed": 0, "false_alarms": 0} for r in OFF_TOPIC_RULES}

    for case in cases:
        s = from_tree(case.tree)
        hits = [{**f, "line": rendered_line(s, f)} for f in findings_of(case.tree)
                if f["rule"] in table]  # fmt: skip

        for rule, (lo, hi) in case.expect.items():
            table[rule]["planted"] += 1
            ok = any(f["rule"] == rule and lo <= f["line"] <= hi for f in hits)
            table[rule]["found" if ok else "missed"] += 1

        for f in hits:
            want = case.expect.get(f["rule"])

            if want is None or not want[0] <= f["line"] <= want[1]:
                table[f["rule"]]["false_alarms"] += 1

    return table


def rendered_line(s: Structure, finding: dict[str, Any]) -> int:
    """A finding's line in the rendered text, from its section, field and line in that field."""
    part = next(p for p in s.parts if p.path == finding["section"])
    block = next(b for b in part.blocks if b.field == finding["field"])

    return s.text.count("\n", 0, block.field_start) + int(finding["line"])


def _column(paragraph: str) -> dict[str, Any]:
    """A column section: its title is the paragraph's first three words."""
    return {"title": " ".join(paragraph.split()[:3]), "text": paragraph}


def build_trees() -> list[tuple[str, dict[str, Any], str | None]]:
    """Section trees shaped like a deck: per pool, three slides of four columns, one paragraph per
    column. Each pool gives an on-topic tree and one whose slide 1, column 2 is a mortgage
    paragraph. Returns (name, tree, path of the off-subject section or None)."""
    _, mortgage = pool("mortgage")
    out: list[tuple[str, dict[str, Any], str | None]] = []

    for subject in SUBJECTS:
        title, paras = pool(subject)

        def deck(swap: bool, title: str = title, paras: list[str] = paras,
                 subject: str = subject) -> dict[str, Any]:  # fmt: skip
            slides = []

            for s, heading in enumerate(HEADINGS[subject]):
                cols = [_column(p) for p in paras[s * 4 : s * 4 + 4]]

                if swap and s == 1:
                    cols[2] = _column(mortgage[2])

                slides.append({"title": heading, "sections": cols})

            return {"title": title, "sections": slides}

        out.append((f"{subject}/deck-on-topic", deck(False), None))
        out.append((f"{subject}/deck-off-column", deck(True), "1.2"))

    return out
