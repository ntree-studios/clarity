"""Phrase backend: spaCy Matcher over lemmas, surface forms and POS tags."""

from __future__ import annotations

from typing import Any

from spacy.language import Language
from spacy.matcher import Matcher
from spacy.tokens import Doc

from clarity.config import Rule
from clarity.matchers.common import CharSpan, dedupe, token_span
from clarity.nlp import concreteness_of


def compile_phrase(nlp: Language, phrase: str, mode: str) -> list[dict[str, Any]]:
    tokens = [t for t in nlp.make_doc(phrase)]

    if mode == "lower":
        return [{"LOWER": t.lower_} for t in tokens]

    lemmas = nlp(phrase)

    return [{"LEMMA": t.lemma_.lower()} for t in lemmas]


def build_matcher(nlp: Language, rule: Rule) -> Matcher:
    matcher = Matcher(nlp.vocab)

    if rule.pattern:
        matcher.add(rule.id, [rule.pattern])

    patterns = [compile_phrase(nlp, p, rule.match) for p in rule.phrases]
    # Hyphenated and capitalized fixed phrases lemmatize differently alone and in context.
    patterns += [compile_phrase(nlp, p, "lower") for p in rule.lower_phrases]

    if patterns:
        matcher.add(rule.id, patterns)

    return matcher


def governor(doc: Doc, start: int, end: int) -> Any:
    """The governed or governing noun of a matched term, or None."""
    head = doc[end - 1]

    for child in head.children:
        if child.lower_ == "of":
            for grand in child.children:
                if grand.dep_ == "pobj":
                    return grand

        if child.dep_ == "dobj":
            return child

    if head.dep_ in {"amod", "compound", "nmod", "appos"} and head.head.pos_ in {"NOUN", "PROPN"}:
        return head.head

    return None


def _abstract_governor(doc: Doc, start: int, end: int, limit: float) -> bool:
    gov = governor(doc, start, end)

    if gov is None:
        return False

    score = concreteness_of(gov)

    return score is not None and score < limit


def run(doc: Doc, rule: Rule, nlp: Language, matcher: Matcher) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for _, start, end in matcher(doc):
        if rule.next_lemma and not (
            end < len(doc) and doc[end].lemma_.lower() in rule.next_lemma
        ):
            continue  # the announcing use is a subject followed by its verb

        if rule.concreteness_max is not None and not _abstract_governor(
            doc, start, end, rule.concreteness_max
        ):
            continue

        spans.append(token_span(doc, start, end))

    return dedupe(spans)
