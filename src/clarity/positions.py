"""Position filters and counting units.

Position filters the match set before counting: a match failing the test is not a finding and
does not consume allowance. Units are what a non-document allowance is measured against.
"""

from __future__ import annotations

from bisect import bisect_right

from spacy.tokens import Doc, Span

from clarity.clauses import Clause
from clarity.markdown import paragraph_ranges
from clarity.matchers.common import sentences


def _content(sent: Span) -> list[int]:
    return [t.i for t in sent if not t.is_punct and not t.is_space]


class Units:
    """Per-document lookup tables for position tests and allowance units."""

    def __init__(
        self,
        doc: Doc,
        text: str,
        sections: list[tuple[int, int]],
        clause_list: list[Clause],
    ) -> None:
        self.doc = doc
        self.sections = sections
        self.section_starts = [start for start, _ in sections]
        self.paragraph_starts = [start for start, _ in paragraph_ranges(text)]
        self.clause_initials = {c.first.i for c in clause_list}
        self.clause_of = {t.i: c.head.i for c in clause_list for t in c.tokens}
        self.final_sentences = self._final_sentences(doc, sections)
        self.paragraph_final = self._final_sentences(doc, paragraph_ranges(text))

    @staticmethod
    def _final_sentences(doc: Doc, sections: list[tuple[int, int]]) -> set[int]:
        """Start token of the last sentence in each range (section or paragraph)."""
        finals: set[int] = set()

        for start, end in sections:
            inside = [s for s in sentences(doc) if start <= s.start_char < end]

            if inside:
                finals.add(inside[-1].start)

        return finals

    def keep(self, position: str, span: Span) -> bool:
        if position == "anywhere":
            return True

        sent = span.sent
        words = _content(sent)

        if position == "sentence-initial":
            return bool(words) and span.start == words[0]

        if position == "sentence-final":
            return bool(words) and span.end - 1 == words[-1]

        if position == "clause-initial":
            return span.start in self.clause_initials

        if position == "paragraph-final":
            return sent.start in self.paragraph_final

        if position == "section-final":
            return sent.start in self.final_sentences

        raise ValueError(f"unknown position {position!r}")

    def unit(self, count_scope: str, span: Span, start_char: int) -> int:
        if count_scope == "section":
            return bisect_right(self.section_starts, start_char)

        if count_scope == "paragraph":
            return bisect_right(self.paragraph_starts, start_char)

        if count_scope == "sentence":
            return int(span.sent.start)

        if count_scope == "clause":
            return self.clause_of.get(span.start, -1)

        return 0
