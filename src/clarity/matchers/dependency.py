"""Dependency backend: spaCy DependencyMatcher over clause structure."""

from __future__ import annotations

from typing import Any

from spacy.language import Language
from spacy.matcher import DependencyMatcher
from spacy.tokens import Doc

from clarity.animacy import is_animate
from clarity.config import Rule
from clarity.matchers.common import CharSpan, dedupe, token_span
from clarity.nlp import concreteness_of


def inflections(lemma: str) -> list[str]:
    """Regular inflected forms of a verb: want, wants, wanted, wanting."""
    forms = {lemma, lemma + "ing", lemma + "ed" if not lemma.endswith("e") else lemma + "d"}
    forms.add(lemma + ("es" if lemma.endswith(("s", "sh", "ch", "x", "z", "o")) else "s"))

    if lemma.endswith("e"):
        forms.add(lemma[:-1] + "ing")

    if lemma.endswith("y") and lemma[-2:-1] not in "aeiou":
        forms.update({lemma[:-1] + "ies", lemma[:-1] + "ied"})

    return sorted(forms)


def _with_surface_forms(pattern: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """A copy of the pattern matching verbs by inflected surface form instead of lemma.

    spaCy's lemmatizer is wrong for some verbs ("hates" becomes "hat"), so a lemma-only
    match misses them. Returns None when the pattern has no verb lemma list to expand.
    """
    out, changed = [], False

    for node in pattern:
        attrs = dict(node.get("RIGHT_ATTRS", {}))
        lemmas = attrs.get("LEMMA", {})

        if isinstance(lemmas, dict) and "IN" in lemmas and attrs.get("POS") == "VERB":
            del attrs["LEMMA"]
            attrs["LOWER"] = {"IN": sorted({f for lem in lemmas["IN"] for f in inflections(lem)})}
            changed = True

        out.append({**node, "RIGHT_ATTRS": attrs} if "RIGHT_ATTRS" in node else dict(node))

    return out if changed else None


def build_matcher(nlp: Language, rule: Rule) -> DependencyMatcher:
    matcher = DependencyMatcher(nlp.vocab)

    for i, pattern in enumerate(rule.patterns):
        variants = [pattern]
        surface = _with_surface_forms(pattern)

        if surface is not None:
            variants.append(surface)

        matcher.add(f"{rule.id}#{i}", variants)

    return matcher


def _anchor_index(rule: Rule, pattern_ids: list[str]) -> int | None:
    if rule.anchor is None:
        return None

    return pattern_ids.index(rule.anchor)


def _bases(word: str) -> set[str]:
    """Possible base forms of an inflected verb, for when the lemmatizer is wrong."""
    out = {word}

    for suffix, repl in (("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"), ("es", ""), ("s", ""),
                         ("ies", "y"), ("ied", "y")):  # fmt: skip
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            out.add(word[: -len(suffix)] + repl)

    return out


# Without coreference these say nothing about animacy: "It said to do it" has no inanimate noun.
UNRESOLVED_PRONOUNS = {"it", "this", "that", "which", "what", "there"}


def _skip(doc: Doc, rule: Rule, names: list[str], ids: list[int]) -> bool:
    """Apply the rule's subject filters, animacy predicate and exclusions."""
    params = rule.params

    if "subjects" in params or "exclude" in params or params.get("require_inanimate"):
        subj = doc[ids[names.index("subj")]]
        verb_tok = doc[ids[names.index("verb")]]
        verbs = {verb_tok.lemma_.lower(), *_bases(verb_tok.lower_)}
        forms = {subj.lemma_.lower(), subj.lower_}

        if "subjects" in params and not forms & set(params["subjects"]):
            return True

        if params.get("require_inanimate") and (
            is_animate(subj) or subj.lower_ in UNRESOLVED_PRONOUNS
        ):
            return True

        for pair in params.get("exclude", []):
            if forms & set(pair["subjects"]) and verbs & set(pair["verbs"]):
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
