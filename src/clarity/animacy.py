"""Animacy predicate: can this subject plausibly hold wants, beliefs or speech?"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from nltk.corpus import wordnet as wn
from spacy.tokens import Token

from clarity.nlp import concreteness

ANIMATE_ENTS = {"PERSON", "ORG", "NORP", "GPE"}
ANIMATE_ROOTS = ("person.n.01", "animal.n.01", "social_group.n.01")
ANIMATE_PRONOUNS = {
    "i", "we", "you", "he", "she", "they", "who", "whoever",
    "someone", "anyone", "everyone", "everybody", "nobody", "somebody", "one",
}  # fmt: skip


@lru_cache(maxsize=1)
def _roots() -> frozenset[Any]:
    return frozenset(wn.synset(name) for name in ANIMATE_ROOTS)


@lru_cache(maxsize=4096)
def wordnet_animate(lemma: str) -> bool:
    """True when the most frequent noun sense inherits from person, animal or social group."""
    senses = wn.synsets(lemma, pos=wn.NOUN)

    if not senses:
        return False

    first = senses[0]
    lineage = {first, *first.closure(lambda s: s.hypernyms())}

    return bool(lineage & _roots())


def _acronym(token: Token) -> bool:
    """API, SQL, CPU: capitalized tokens for things rather than people."""
    return len(token.text) > 1 and token.text.isupper()


@lru_cache(maxsize=4096)
def _used_as_common_noun(word: str) -> bool:
    """WordNet knows the word as a noun and it is a common word: it has tagged-corpus uses
    ("momentum") or a concreteness rating ("accountability"). A rare sense alone does not count, so
    "Pia" (pia mater) is still a name."""
    senses = wn.synsets(word, pos=wn.NOUN)

    if not senses:
        return False

    lemmas = [lemma for s in senses for lemma in s.lemmas() if lemma.name().lower() == word]

    if any(lemma.count() > 0 for lemma in lemmas):
        return True

    return word in concreteness()


def _capitalized_common_noun(token: Token) -> bool:
    """A sentence-initial word capitalized only by its position: "Trust flows downstream"."""
    first = token.is_sent_start is True and token.ent_type_ == ""

    return first and _used_as_common_noun(token.lower_)


def _looks_like_a_name(token: Token) -> bool:
    """A capitalized singular noun with no determiner ('Pia had seen') is a name the tagger missed.

    Common singular nouns need a determiner, so this separates names from 'Architecture wants'
    only when a determiner is present. A bare capitalized sentence-initial noun is read as a name
    unless WordNet has uses of it as a common noun, so "Momentum fades" stays abstract.
    """
    bare = not any(c.dep_ in {"det", "poss"} for c in token.children)
    capitalized = token.tag_ == "NN" and token.text[:1].isupper() and not _acronym(token)

    return capitalized and bare and not _used_as_common_noun(token.lower_)


# Company and agency acronyms that WordNet does not know and that do act as agents.
ORG_ACRONYMS = {
    "ibm", "amd", "sap", "bbc", "cnn", "hp", "nsa", "cia", "irs", "epa", "fda", "nhs", "sec",
    "dod", "dhs", "nbc", "abc", "cbs", "ups", "gm", "ge", "hsbc", "nyt", "mit", "ucla",
}  # fmt: skip


def _is_org_acronym(token: Token) -> bool:
    """All-caps tokens are agents only when they are a known organization.

    spaCy tags API, SQL and AWS as ORG, but they are things that cannot act. An acronym passes when
    WordNet resolves it to an animate lineage (FBI, NASA, NATO) or it is on the short allowlist.
    """
    word = token.text.lower()

    return word in ORG_ACRONYMS or wordnet_animate(word)


def is_animate(token: Token) -> bool:
    """Ordered checks: NER label, proper noun or animate pronoun, WordNet hypernyms."""
    if _acronym(token):
        return _is_org_acronym(token)

    if token.ent_type_ in ANIMATE_ENTS:
        return True

    if token.lower_ in ANIMATE_PRONOUNS:
        return True  # "No one wants"

    if token.pos_ == "PROPN" and not _acronym(token) and not _capitalized_common_noun(token):
        return True  # names the NER missed ("Pia")

    if token.pos_ == "PRON":
        return False

    if _looks_like_a_name(token):
        return True

    return wordnet_animate(token.lemma_.lower())
