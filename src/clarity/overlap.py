"""Content-lemma extraction and overlap scoring shared by the redundancy features."""

from __future__ import annotations

import math
from collections.abc import Iterable

from spacy.tokens import Doc, Span

CONTENT_POS = frozenset({"NOUN", "PROPN", "VERB", "ADJ", "ADV"})


def content_lemmas(span: Doc | Span) -> set[str]:
    """Lemmatized content words: NOUN, PROPN, VERB, ADJ, ADV. No stopwords."""
    return {t.lemma_.lower() for t in span if t.pos_ in CONTENT_POS and not t.is_stop}


def overlap(a: set[str], b: set[str], idf: dict[str, float] | None = None) -> float:
    """Jaccard similarity, weighted by per-lemma IDF when given.

    A lemma missing from idf weighs 1.0. When every weight in the union is zero the score falls
    back to plain Jaccard, which is what a one-paragraph document needs.
    """
    union = a | b

    if not union:
        return 0.0

    shared = a & b
    plain = len(shared) / len(union)

    if idf is None:
        return plain

    total = sum(idf.get(w, 1.0) for w in union)

    if total == 0:
        return plain

    return sum(idf.get(w, 1.0) for w in shared) / total


def paragraph_idf(paragraphs: Iterable[set[str]]) -> dict[str, float]:
    """IDF of each lemma over paragraphs: log((N + 1) / (df + 1)).

    A lemma in every paragraph weighs 0, so the document's topic noun adds nothing to overlap.
    """
    sets = list(paragraphs)
    frequency: dict[str, int] = {}

    for lemmas in sets:
        for lemma in lemmas:
            frequency[lemma] = frequency.get(lemma, 0) + 1

    return {w: math.log((len(sets) + 1) / (df + 1)) for w, df in frequency.items()}
