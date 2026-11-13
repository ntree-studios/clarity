"""Repeated n-grams inside one document: the mechanism behind every tic before anyone names it."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from spacy.tokens import Doc, Token

DEFAULT_SKIP_POS = {"DET", "ADP", "PRON", "AUX", "PART", "CCONJ", "SCONJ"}


@dataclass
class Repeat:
    """A phrase used several times, with the character spans of each kept occurrence."""

    phrase: str
    n: int
    spans: list[tuple[int, int]]


def _words(doc: Doc) -> list[Token]:
    return [t for t in doc if not t.is_punct and not t.is_space]


def repeated_ngrams(
    doc: Doc,
    sizes: tuple[int, ...] = (2, 3, 4),
    min_occurrences: int = 3,
    min_words_apart: int = 40,
    skip_pos: set[str] | None = None,
    exclude_proper_nouns: bool = True,
) -> list[Repeat]:
    """Phrases occurring at least min_occurrences times, spaced apart, longest first.

    Dropped: n-grams of function words only, n-grams that start or end on a function word,
    n-grams containing a proper noun, and occurrences closer than min_words_apart to the
    previous kept one (lists and parallel structure are legitimate). A shorter n-gram wholly
    inside a longer reported one is suppressed.
    """
    skip = DEFAULT_SKIP_POS if skip_pos is None else skip_pos
    words = _words(doc)
    covered: set[int] = set()
    found: list[Repeat] = []

    for n in sorted(sizes, reverse=True):
        grams: dict[tuple[str, ...], list[int]] = defaultdict(list)

        for i in range(len(words) - n + 1):
            seg = words[i : i + n]

            if len({t.sent.start for t in seg}) > 1 or seg[0].pos_ in skip or seg[-1].pos_ in skip:
                continue

            if not all(t.is_alpha for t in seg):
                continue  # symbols, digits and code fragments are not phrases

            if exclude_proper_nouns and any(t.pos_ == "PROPN" for t in seg):
                continue

            grams[tuple(t.lemma_.lower() for t in seg)].append(i)

        for positions in grams.values():
            kept: list[int] = []

            for i in positions:
                if not kept or i - kept[-1] >= min_words_apart:
                    kept.append(i)

            fully_inside = all(all(i + k in covered for k in range(n)) for i in kept)

            if len(kept) < min_occurrences or fully_inside:
                continue

            for i in kept:
                covered.update(range(i, i + n))

            spans = [
                (words[i].idx, words[i + n - 1].idx + len(words[i + n - 1].text)) for i in kept
            ]
            found.append(Repeat(doc.text[spans[0][0] : spans[0][1]].lower(), n, spans))

    return sorted(found, key=lambda r: r.spans[0][0])
