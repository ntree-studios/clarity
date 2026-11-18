"""Phrase backend: spaCy Matcher over lemmas, surface forms and POS tags."""

from __future__ import annotations

from typing import Any

from spacy.language import Language
from spacy.matcher import Matcher
from spacy.tokens import Doc, Token

from clarity.config import Rule
from clarity.matchers.common import CharSpan, dedupe, token_span
from clarity.nlp import concreteness_of


def _sent_end(token: Token) -> bool:
    """The last word or mark of a sentence. Whitespace between fields stays in the sentence before
    it, so a token followed only by whitespace up to the next sentence also ends its sentence."""
    if token.is_space:
        return False

    doc = token.doc
    i = token.i + 1

    while i < len(doc) and doc[i].is_space and not doc[i].is_sent_start:
        i += 1

    return i >= len(doc) or bool(doc[i].is_sent_start)


# Patterns write {"_": {"sent_end": true}} for the last token of a sentence. Every title, subtitle,
# item and paragraph starts a sentence, so this also marks the end of a field with no period.
if not Token.has_extension("sent_end"):
    Token.set_extension("sent_end", getter=_sent_end)


def compile_phrase(nlp: Language, phrase: str, mode: str) -> list[dict[str, Any]]:
    tokens = [t for t in nlp.make_doc(phrase)]

    if mode == "lower":
        return [{"LOWER": t.lower_} for t in tokens]

    lemmas = nlp(phrase)

    return [{"LEMMA": t.lemma_.lower()} for t in lemmas]


def build_matcher(nlp: Language, rule: Rule) -> Matcher:
    matcher = Matcher(nlp.vocab)

    if rule.pattern:
        # One token pattern, or a list of them when the first item is itself a list.
        several = isinstance(rule.pattern[0], list)
        matcher.add(rule.id, rule.pattern if several else [rule.pattern])

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
