"""Animacy predicate: can this subject plausibly hold wants, beliefs or speech?"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from nltk.corpus import wordnet as wn
from spacy.tokens import Token

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


def is_animate(token: Token) -> bool:
    """Ordered checks: NER label, WordNet hypernyms, animate pronoun. Otherwise inanimate."""
    if token.ent_type_ in ANIMATE_ENTS:
        return True

    if token.pos_ == "PRON":
        return token.lower_ in ANIMATE_PRONOUNS

    return wordnet_animate(token.lemma_.lower())
