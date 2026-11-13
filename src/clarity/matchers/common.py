"""Shared helpers for matcher backends."""

from __future__ import annotations

from spacy.tokens import Doc, Span

CharSpan = tuple[int, int]
CONJ = {"and", "but", "so", "yet", "or"}


def token_span(doc: Doc, start: int, end: int) -> CharSpan:
    """Character span of tokens [start, end)."""
    last = doc[end - 1]

    return doc[start].idx, last.idx + len(last.text)


def clause_initial(doc: Doc, start: int) -> bool:
    i = start

    while i > 0 and doc[i - 1].lower_ in CONJ:
        i -= 1

    if i == 0 or doc[i].is_sent_start:
        return True

    prev = doc[i - 1]

    return prev.is_punct or prev.is_space


def dedupe(spans: list[CharSpan]) -> list[CharSpan]:
    """Drop spans overlapping an earlier or longer one."""
    kept: list[CharSpan] = []

    for span in sorted(set(spans), key=lambda s: (s[0], -(s[1] - s[0]))):
        if not kept or span[0] >= kept[-1][1]:
            kept.append(span)

    return kept


def sentences(doc: Doc) -> list[Span]:
    """Sentences with surrounding whitespace tokens trimmed; empty ones dropped."""
    out = []

    for sent in doc.sents:
        start, end = sent.start, sent.end

        while start < end and doc[start].is_space:
            start += 1

        while end > start and doc[end - 1].is_space:
            end -= 1

        if any(not t.is_punct for t in doc[start:end]):
            out.append(doc[start:end])

    return out
