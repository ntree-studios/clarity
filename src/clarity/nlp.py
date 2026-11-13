"""spaCy pipeline and concreteness-norm loading."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import spacy
from spacy.language import Language

MODEL = "en_core_web_sm"


class ModelError(RuntimeError):
    """Raised when the baked spaCy model is not installed."""


@lru_cache(maxsize=1)
def get_nlp() -> Language:
    try:
        return spacy.load(MODEL)
    except OSError as exc:
        raise ModelError(f"spaCy model {MODEL} is not installed") from exc


@lru_cache(maxsize=1)
def concreteness() -> dict[str, float]:
    table: dict[str, float] = {}
    text = resources.files("clarity").joinpath("data/concreteness.tsv").read_text("utf-8")

    for line in text.splitlines():
        word, _, score = line.partition("\t")

        if word and score:
            table[word] = float(score)

    return table


def concreteness_of(token: Any) -> float | None:
    """Mean concreteness rating (1 abstract to 5 concrete) or None when unrated."""
    table = concreteness()

    return table.get(token.lemma_.lower(), table.get(token.lower_))
