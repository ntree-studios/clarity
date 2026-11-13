"""Readability metrics, reported separately from the style score."""

from __future__ import annotations

import math
import re
from typing import Any

from spacy.tokens import Doc

from clarity.matchers.common import sentences

GRADE_METRICS = ("flesch_kincaid_grade", "gunning_fog", "smog", "coleman_liau", "ari")


def count_syllables(word: str) -> int:
    """Vowel-group heuristic with silent-e handling."""
    w = re.sub(r"[^a-z]", "", word.lower())

    if not w:
        return 0

    if len(w) <= 3:
        return 1

    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)

    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def metrics(
    words: int, sentences: int, syllables: int, letters: int, complex_words: int
) -> dict[str, float]:
    """The six published formulas from raw counts."""
    if words == 0 or sentences == 0:
        return {
            k: 0.0
            for k in ("flesch_reading_ease", *GRADE_METRICS)
        }

    wps = words / sentences
    spw = syllables / words
    letters_per_100 = letters / words * 100
    sentences_per_100 = sentences / words * 100

    return {
        "flesch_reading_ease": 206.835 - 1.015 * wps - 84.6 * spw,
        "flesch_kincaid_grade": 0.39 * wps + 11.8 * spw - 15.59,
        "gunning_fog": 0.4 * (wps + 100 * complex_words / words),
        "smog": 1.043 * math.sqrt(complex_words * (30 / sentences)) + 3.1291,
        "coleman_liau": 0.0588 * letters_per_100 - 0.296 * sentences_per_100 - 15.8,
        "ari": 4.71 * (letters / words) + 0.5 * wps - 21.43,
    }


def document_counts(doc: Doc) -> dict[str, int]:
    words = [t for t in doc if t.is_alpha or t.like_num]
    syl = [count_syllables(t.text) for t in words]

    return {
        "words": len(words),
        "sentences": len(sentences(doc)),
        "syllables": sum(syl),
        "letters": sum(sum(c.isalpha() for c in t.text) for t in words),
        "complex_words": sum(1 for n in syl if n >= 3),
    }


def report(doc: Doc, settings: dict[str, Any]) -> dict[str, Any]:
    """The readability object for the output."""
    values = metrics(**document_counts(doc))
    low, high = settings["target_grade"]
    grade = sum(values[k] for k in GRADE_METRICS) / len(GRADE_METRICS)
    counted = document_counts(doc)["words"] > 0
    band_on = float(settings.get("weight", 1.0)) != 0.0

    return {
        "metrics": {k: round(v, 2) for k, v in values.items()},
        "grade": round(grade, 2),
        "target_grade": [low, high],
        "inside_band": bool(counted and low <= grade <= high) if band_on else None,
        "fail_outside_band": bool(settings.get("fail_outside_band", False)) and band_on,
    }
