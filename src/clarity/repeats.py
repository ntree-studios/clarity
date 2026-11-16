"""Repeated n-grams inside one document: the mechanism behind every tic, found before anyone
has a name for it."""

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


def _compound(seg: list[Token]) -> bool:
    """A noun with only compound modifiers before it, all inside the n-gram."""
    head = seg[-1]

    modifiers = seg[:-1]

    return head.pos_ == "NOUN" and all(t.dep_ == "compound" and t.head.i == head.i
                                       for t in modifiers)  # fmt: skip


def _key_term(words: list[Token], positions: list[int], n: int, min_outside: int) -> bool:
    """One of the phrase's nouns occurs min_outside times or more outside every occurrence."""
    inside = {i + k for i in positions for k in range(n)}
    first = positions[0]
    nouns = {words[first + k].lemma_.lower() for k in range(n) if words[first + k].pos_ == "NOUN"}
    outside: dict[str, int] = defaultdict(int)

    for j, t in enumerate(words):
        if j not in inside and t.pos_ == "NOUN" and t.lemma_.lower() in nouns:
            outside[t.lemma_.lower()] += 1

    return any(c >= min_outside for c in outside.values())


def repeated_ngrams(
    doc: Doc,
    sizes: tuple[int, ...] = (2, 3, 4),
    min_occurrences: int = 3,
    min_words_apart: int = 40,
    skip_pos: set[str] | None = None,
    exclude_proper_nouns: bool = True,
    skip_compounds: bool = False,
    key_term_min: int = 0,
) -> list[Repeat]:
    """Phrases occurring at least min_occurrences times, spaced apart, longest first.

    Dropped: n-grams of function words only, n-grams that start or end on a function word,
    n-grams containing a proper noun, and occurrences closer than min_words_apart to the
    previous kept one (lists and parallel structure are legitimate). A shorter n-gram wholly
    inside a longer reported one is suppressed.

    skip_compounds drops noun compounds such as "interest rate" and "espresso shot", which are
    terminology. key_term_min > 0 drops a phrase when one of its nouns also occurs at least that
    many times outside the phrase, because such a noun is a subject of the text.
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

            if skip_compounds and _compound(seg):
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

            if key_term_min and _key_term(words, positions, n, key_term_min):
                continue

            for i in kept:
                covered.update(range(i, i + n))

            spans = [
                (words[i].idx, words[i + n - 1].idx + len(words[i + n - 1].text)) for i in kept
            ]
            found.append(Repeat(doc.text[spans[0][0] : spans[0][1]].lower(), n, spans))

    return sorted(found, key=lambda r: r.spans[0][0])
