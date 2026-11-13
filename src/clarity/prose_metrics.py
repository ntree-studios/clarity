"""Document-level measurements with no single sentence to blame. Advisory and unscored."""

from __future__ import annotations

import importlib
import re
import statistics
from collections.abc import Callable
from typing import Any

from spacy.tokens import Doc

from clarity.markdown import paragraph_ranges, prose_paragraphs
from clarity.matchers.common import sentences
from clarity.metrics import REGISTRY, Analysis, metric
from clarity.nlp import concreteness_of
from clarity.overlap import content_lemmas

CONTENT = {"NOUN", "VERB", "ADJ", "ADV", "PROPN"}
FUNCTION = {"DET", "ADP", "AUX", "CCONJ", "SCONJ", "PRON", "PART"}
ANAPHORA = {"he", "she", "it", "they", "him", "her", "them", "his", "its", "their", "this", "these"}
MTLD_THRESHOLD = 0.72
LOWEST_SHOWN = 3
importlib.import_module("clarity.metrics_structure")  # registers the structure metrics


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def sentence_length_variance(doc: Doc, text: str) -> dict[str, Any]:
    lengths = [sum(1 for t in s if not t.is_punct and not t.is_space) for s in sentences(doc)]

    if not lengths:
        return {"mean": None, "sd": None, "sentences": 0}

    return {
        "mean": _round(statistics.fmean(lengths)),
        "sd": _round(statistics.pstdev(lengths)),
        "sentences": len(lengths),
    }


def paragraph_length_distribution(doc: Doc, text: str) -> dict[str, Any]:
    sizes = []

    for start, end in paragraph_ranges(text):
        body = "\n".join(
            line for line in text[start:end].splitlines() if not line.lstrip().startswith("#")
        )
        count = len(re.findall(r"\w+", body))

        if count:
            sizes.append(count)

    if not sizes:
        return {"count": 0, "mean": None, "sd": None, "min": None, "max": None}

    return {
        "count": len(sizes),
        "mean": _round(statistics.fmean(sizes)),
        "sd": _round(statistics.pstdev(sizes)),
        "min": min(sizes),
        "max": max(sizes),
    }


def _mtld_pass(tokens: list[str]) -> float:
    factors, seen, count = 0.0, set(), 0

    for tok in tokens:
        seen.add(tok)
        count += 1

        if len(seen) / count <= MTLD_THRESHOLD:
            factors += 1
            seen, count = set(), 0

    if count:
        factors += (1 - len(seen) / count) / (1 - MTLD_THRESHOLD)

    return len(tokens) / factors if factors else float(len(tokens))


def lexical_diversity(doc: Doc, text: str) -> dict[str, Any]:
    """MTLD: how long a run of text keeps type-token ratio above 0.72. Length independent."""
    tokens = [t.lemma_.lower() for t in doc if t.is_alpha]

    if len(tokens) < 20:
        return {"mtld": None, "tokens": len(tokens)}

    mtld = (_mtld_pass(tokens) + _mtld_pass(tokens[::-1])) / 2

    return {"mtld": _round(mtld), "tokens": len(tokens)}


def content_word_ratio(doc: Doc, text: str) -> dict[str, Any]:
    content = sum(1 for t in doc if t.pos_ in CONTENT)
    function = sum(1 for t in doc if t.pos_ in FUNCTION)

    return {
        "ratio": _round(content / function) if function else None,
        "content": content,
        "function": function,
    }


def given_new_ordering(doc: Doc, text: str) -> dict[str, Any]:
    """Share of sentences whose first content word was already used in the previous two.

    Known information should precede new information. A low share reads as disconnected even
    when every sentence is clean.
    """
    sents = sentences(doc)
    lemmas = [[t.lemma_.lower() for t in s if t.pos_ in CONTENT] for s in sents]
    linked = evaluated = 0

    for i in range(1, len(sents)):
        if not lemmas[i]:
            continue

        evaluated += 1
        earlier = {w for prior in lemmas[max(0, i - 2) : i] for w in prior}
        linked += lemmas[i][0] in earlier

    return {
        "proportion": _round(linked / evaluated) if evaluated else None,
        "evaluated": evaluated,
    }


def referential_density(doc: Doc, text: str) -> dict[str, Any]:
    words = sum(1 for t in doc if not t.is_punct and not t.is_space)
    refs = [t for t in doc if t.pos_ == "PRON" or t.lower_ == "the"]
    gaps = []

    for tok in doc:
        if tok.lower_ not in ANAPHORA:
            continue

        prior = [t.i for t in doc[: tok.i] if t.pos_ in {"NOUN", "PROPN"}]

        if prior:
            gaps.append(tok.i - prior[-1])

    return {
        "per_1k": _round(len(refs) * 1000 / words) if words else 0.0,
        "mean_antecedent_distance": _round(statistics.fmean(gaps)) if gaps else None,
    }


def mean_concreteness(doc: Doc, text: str) -> dict[str, Any]:
    rated = [(t, concreteness_of(t)) for t in doc if t.pos_ in CONTENT]
    scores = [s for _, s in rated if s is not None]

    return {
        "mean": _round(statistics.fmean(scores)) if scores else None,
        "coverage": _round(len(scores) / len(rated)) if rated else None,
    }


def novelty_rate(doc: Doc, text: str) -> dict[str, Any]:
    """New content lemmas per sentence, counted against what the paragraph already said.

    The first sentence of a paragraph has nothing to be new against, so it is not scored.
    Diagnostic: the paragraphs with the lowest rate are named by line, without blaming a sentence.
    """
    sents = sentences(doc)
    rows: list[tuple[float, int, int]] = []

    for start, end in prose_paragraphs(text):
        group = [s for s in sents if start <= s.start_char < end]
        seen = content_lemmas(group[0]) if group else set()
        added = []

        for sent in group[1:]:
            lemmas = content_lemmas(sent)
            added.append(len(lemmas - seen))
            seen |= lemmas

        if added:
            rows.append((sum(added) / len(added), text.count("\n", 0, start) + 1, len(added)))

    evaluated = sum(n for _, _, n in rows)
    pooled = sum(rate * n for rate, _, n in rows) / evaluated if evaluated else None
    lowest = sorted(rows, key=lambda r: (r[0], r[1]))[:LOWEST_SHOWN]

    return {
        "per_sentence": _round(pooled),
        "paragraphs_scored": len(rows),
        "lowest_paragraphs": [{"line": line, "rate": _round(rate)} for rate, line, _ in lowest],
    }


LEGACY = {
    "sentence_length_variance": (sentence_length_variance, ("sd",)),
    "paragraph_length_distribution": (paragraph_length_distribution, ("mean",)),
    "lexical_diversity": (lexical_diversity, ("mtld",)),
    "content_word_ratio": (content_word_ratio, ("ratio",)),
    "given_new_ordering": (given_new_ordering, ("proportion",)),
    "referential_density": (referential_density, ("per_1k", "mean_antecedent_distance")),
    "mean_concreteness": (mean_concreteness, ("mean",)),
    "novelty_rate": (novelty_rate, ("per_sentence",)),
}


def _register(
    fn: Callable[[Doc, str], dict[str, Any]], scalars: tuple[str, ...], name: str
) -> None:
    metric(name, scalars=scalars)(lambda a: fn(a.doc, a.text))


for _name, (_fn, _scalars) in LEGACY.items():
    _register(_fn, _scalars, _name)


def report(analysis: Analysis, settings: dict[str, Any]) -> dict[str, Any]:
    wanted = settings.get("report") or list(REGISTRY)

    return {
        "weight": float(settings.get("weight", 0.0)),
        "advisory": True,
        "metrics": {name: analysis.get(name) for name in wanted if name in REGISTRY},
    }
