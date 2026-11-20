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


@lru_cache(maxsize=1)
def _first_names() -> frozenset[str]:
    """NLTK's name list. A word that is also a verb is a person's name when it is on it ("Will",
    "Pat", "Mark") and a command or feature when it is not ("Format", "Sync", "Validate")."""
    from nltk.corpus import names

    return frozenset(name.lower() for name in names.words())


@lru_cache(maxsize=4096)
def _names_a_command(word: str) -> bool:
    """A verb in WordNet that is not a first name, a role or a known entity: "Validate says".

    WordNet lists Google as an instance of a search engine, so "Google says" stays a company.
    """

    senses = wn.synsets(word)
    verb = any(s.pos() == wn.VERB for s in senses)
    entity = any(s.instance_hypernyms() for s in senses)
    person = any(_is_person_sense(s) for s in senses if s.pos() == wn.NOUN)

    return verb and not entity and not person and word not in _first_names()


def _is_person_sense(sense: Any) -> bool:
    person = wn.synset("person.n.01")

    return person in {sense, *sense.closure(lambda x: x.hypernyms() + x.instance_hypernyms())}


def _in_computing(sense: Any) -> bool:
    return any(d.name().startswith("computer_science") for d in sense.topic_domains())


@lru_cache(maxsize=4096)
def _software_sense(lemma: str) -> bool:
    """WordNet files a noun sense under computer science and the person senses are no more frequent
    in tagged text: "compiler", "server" and "driver" are software, "editor" and "manager" are
    people."""
    senses = wn.synsets(lemma, pos=wn.NOUN)

    def uses(sense: Any) -> int:
        return sum(x.count() for x in sense.lemmas() if x.name().lower() == lemma)

    software = sum(uses(s) for s in senses if _in_computing(s))
    people = sum(uses(s) for s in senses if _is_person_sense(s))

    return any(_in_computing(s) for s in senses) and people <= software


def _capitalized_common_noun(token: Token) -> bool:
    """A sentence-initial word capitalized only by its position: "Trust flows downstream"."""
    first = token.is_sent_start is True and token.ent_type_ == ""

    known_word = _used_as_common_noun(token.lower_) or _names_a_command(token.lower_)

    return first and known_word


def _looks_like_a_name(token: Token) -> bool:
    """A capitalized singular noun with no determiner ('Pia had seen') is a name the tagger missed.

    Common singular nouns need a determiner, so this separates names from 'Architecture wants'
    only when a determiner is present. A bare capitalized sentence-initial noun is read as a name
    unless WordNet has uses of it as a common noun, so "Momentum fades" stays abstract.
    """
    bare = not any(c.dep_ in {"det", "poss"} for c in token.children)
    capitalized = token.tag_ == "NN" and token.text[:1].isupper() and not _acronym(token)

    known_word = _used_as_common_noun(token.lower_) or _names_a_command(token.lower_)

    return capitalized and bare and not known_word


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


def _command_named_feature(token: Token) -> bool:
    """A sentence-initial word that is a verb but not a first name ("Validate says", "Format tells
    you"): a command or feature name, whatever label the NER gave it."""
    first = token.is_sent_start is True and not _acronym(token)

    return first and token.ent_type_ != "GPE" and _names_a_command(token.lower_)


def is_animate(token: Token) -> bool:
    """Ordered checks: NER label, proper noun or animate pronoun, WordNet hypernyms."""
    if _acronym(token):
        return _is_org_acronym(token)

    if _command_named_feature(token) or _software_sense(token.lemma_.lower()):
        return False

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
