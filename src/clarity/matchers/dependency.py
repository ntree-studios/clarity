"""Dependency backend: spaCy DependencyMatcher over clause structure."""

from __future__ import annotations

from spacy.language import Language
from spacy.matcher import DependencyMatcher
from spacy.tokens import Doc

from clarity.animacy import is_animate
from clarity.config import Rule
from clarity.matchers.common import CharSpan, dedupe, token_span
from clarity.nlp import concreteness_of


def build_matcher(nlp: Language, rule: Rule) -> DependencyMatcher:
    matcher = DependencyMatcher(nlp.vocab)

    for i, pattern in enumerate(rule.patterns):
        matcher.add(f"{rule.id}#{i}", [pattern])

    return matcher


def _anchor_index(rule: Rule, pattern_ids: list[str]) -> int | None:
    if rule.anchor is None:
        return None

    return pattern_ids.index(rule.anchor)


def _skip(doc: Doc, rule: Rule, names: list[str], ids: list[int]) -> bool:
    """Apply the rule's subject filters, animacy predicate and exclusions."""
    params = rule.params

    if "subjects" in params or "exclude" in params or params.get("require_inanimate"):
        subj = doc[ids[names.index("subj")]]
        verb = doc[ids[names.index("verb")]].lemma_.lower()
        forms = {subj.lemma_.lower(), subj.lower_}

        if "subjects" in params and not forms & set(params["subjects"]):
            return True

        if params.get("require_inanimate") and is_animate(subj):
            return True

        for pair in params.get("exclude", []):
            if forms & set(pair["subjects"]) and verb in pair["verbs"]:
                return True

    return False


def _too_concrete(doc: Doc, rule: Rule, names: list[str], ids: list[int]) -> bool:
    if rule.concreteness_max is None:
        return False

    idx = _anchor_index(rule, names)

    if idx is None:
        return True

    score = concreteness_of(doc[ids[idx]])

    return score is None or score >= rule.concreteness_max


def run(doc: Doc, rule: Rule, nlp: Language, matcher: DependencyMatcher) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for match_id, token_ids in matcher(doc):
        key = nlp.vocab.strings[match_id]
        names = [node["RIGHT_ID"] for node in rule.patterns[int(key.rsplit("#", 1)[1])]]

        if _skip(doc, rule, names, token_ids) or _too_concrete(doc, rule, names, token_ids):
            continue

        spans.append(token_span(doc, min(token_ids), max(token_ids) + 1))

    return dedupe(spans)
