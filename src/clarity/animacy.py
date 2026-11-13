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


def _acronym(token: Token) -> bool:
    """API, SQL, CPU: capitalized tokens that name things, not people."""
    return len(token.text) > 1 and token.text.isupper()


def _looks_like_a_name(token: Token) -> bool:
    """A capitalized singular noun with no determiner ('Pia had seen') is a name the tagger missed.

    Common singular nouns need a determiner, so this separates names from 'Architecture wants'
    only when a determiner is present; a bare capitalized sentence-initial noun is read as a name.
    """
    bare = not any(c.dep_ in {"det", "poss"} for c in token.children)

    return token.tag_ == "NN" and token.text[:1].isupper() and bare and not _acronym(token)


# Company and agency acronyms that WordNet does not know and that do act as agents.
ORG_ACRONYMS = {
    "ibm", "amd", "sap", "bbc", "cnn", "hp", "nsa", "cia", "irs", "epa", "fda", "nhs", "sec",
    "dod", "dhs", "nbc", "abc", "cbs", "ups", "gm", "ge", "hsbc", "nyt", "mit", "ucla",
}  # fmt: skip


def _is_org_acronym(token: Token) -> bool:
    """All-caps tokens are agents only when they are a known organization.

    spaCy tags API, SQL and AWS as ORG, but they name things, not actors. An acronym passes when
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

    if token.lower_ in ANIMATE_PRONOUNS or (token.pos_ == "PROPN" and not _acronym(token)):
        return True  # names the NER missed ("Pia"), and "No one wants"

    if token.pos_ == "PRON":
        return False

    if _looks_like_a_name(token):
        return True

    return wordnet_animate(token.lemma_.lower())
