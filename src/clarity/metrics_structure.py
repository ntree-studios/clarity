"""Structure, variety, register and document metrics. Computed from the parse, never scored."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any

from spacy.tokens import Span, Token

from clarity.clauses import SUBJECT_DEPS, VERBAL, Clause
from clarity.metrics import Analysis, metric
from clarity.overlap import content_lemmas

DEPENDENT_DEPS = {"relcl", "advcl", "ccomp", "acl", "csubj", "csubjpass"}
SENTENCE_TYPES = ("simple", "compound", "complex", "compound-complex", "fragment")
OPENERS = ("subject", "prepositional-phrase", "subordinate-clause", "coordinating-conjunction",
           "adverbial", "participial", "other")  # fmt: skip
MODALS = {"would", "could", "should", "might", "may", "must"}
SINGULAR_PRONOUNS = {"it", "its", "this"}
PLURAL_PRONOUNS = {"they", "them", "their", "these", "those"}
PERSON_PRONOUNS = {"he", "she", "him", "her", "his", "hers"}
LOOKBACK = 60
# The tagger reads an imperative like "Run the tests" as AUX or VBP, so forms are grouped.
FORMS = {"VB": "base", "VBP": "base", "VBZ": "3sg", "VBG": "gerund", "VBD": "past", "VBN": "past"}
SPAN_SCOPES = ("sentence", "paragraph", "document")


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def _per_1k(count: int, words: int) -> float:
    return _round(count * 1000 / words) or 0.0 if words else 0.0


def _independent(head: Token) -> bool:
    """A clause head with a subject, no mark child, and a dependency that is not subordinate.

    A coordinated head takes the status of the clause it is coordinated with.
    """
    node = head

    while node.dep_ == "conj" and node.head.i != node.i:
        node = node.head

    return node.dep_ not in DEPENDENT_DEPS and not any(c.dep_ == "mark" for c in node.children)


@dataclass
class SentenceInfo:
    span: Span
    independent: int
    dependent: int
    kind: str
    opener: str
    depth: int


def _depth(token: Token) -> int:
    depth = 0

    while token.head.i != token.i:
        token = token.head
        depth += 1

    return depth


def _kind(root: Token, independent: int, dependent: int) -> str:
    if root.pos_ not in VERBAL:
        return "fragment"

    if independent >= 2:
        return "compound-complex" if dependent else "compound"

    return "complex" if dependent else "simple"


def _opener(sent: Span) -> str:
    first = next((t for t in sent if t.is_alpha or t.is_digit), None)

    if first is None:
        return "other"

    if first.pos_ == "CCONJ":
        return "coordinating-conjunction"

    if first.pos_ == "SCONJ" or first.dep_ == "mark":
        return "subordinate-clause"

    if first.pos_ == "ADP":
        return "prepositional-phrase"

    if first.pos_ == "ADV":
        return "adverbial"

    if first.pos_ == "VERB" and first.tag_ in {"VBG", "VBN"}:
        return "participial"

    node = first

    while True:
        if node.dep_ in SUBJECT_DEPS:
            return "subject"

        if node.head.i == node.i:
            return "other"

        node = node.head


def _sentence_infos(a: Analysis) -> list[SentenceInfo]:
    by_sentence: dict[int, list[Clause]] = {}

    for clause in a.clauses:
        by_sentence.setdefault(clause.head.sent.start, []).append(clause)

    out = []

    for sent in a.sentences:
        group = by_sentence.get(sent.start, [])
        independent = sum(1 for c in group if _independent(c.head))
        dependent = len(group) - independent

        if sent.root.pos_ in VERBAL:
            independent = max(independent, 1)

        kind = _kind(sent.root, independent, dependent)
        depth = max((_depth(t) for t in sent), default=0)
        out.append(SentenceInfo(sent, independent, dependent, kind, _opener(sent), depth))

    return out


def infos(a: Analysis) -> list[SentenceInfo]:
    if "_infos" not in a._cache:
        a._cache["_infos"] = _sentence_infos(a)

    return a._cache["_infos"]  # type: ignore[no-any-return]


# ---- sentence structure -------------------------------------------------------------------


@metric("sentence_type_distribution", scopes=("sentence", "document"),
        scalars=tuple(f"shares.{t}" for t in SENTENCE_TYPES))  # fmt: skip
def sentence_type_distribution(a: Analysis) -> dict[str, Any]:
    """Simple, compound, complex, compound-complex and fragment sentences, counted and as shares."""
    counts = Counter(i.kind for i in infos(a))
    total = sum(counts.values())

    return {
        "counts": {t: counts.get(t, 0) for t in SENTENCE_TYPES},
        "shares": {t: _round(counts.get(t, 0) / total) if total else None for t in SENTENCE_TYPES},
        "max_share": _round(max(counts.values()) / total) if total else None,
        "sentences": total,
    }


@metric("subordination_index", scopes=SPAN_SCOPES, scalars=("value",))
def subordination_index(a: Analysis) -> dict[str, Any]:
    """Dependent clauses per independent clause."""
    ind = sum(i.independent for i in infos(a))
    dep = sum(i.dependent for i in infos(a))

    return {"value": _round(dep / ind) if ind else None, "independent": ind, "dependent": dep}


@metric("coordination_subordination_ratio", scopes=SPAN_SCOPES, scalars=("value",))
def coordination_subordination_ratio(a: Analysis) -> dict[str, Any]:
    """Coordinated independent clauses per dependent clause."""
    coordinated = sum(max(0, i.independent - 1) for i in infos(a))
    dep = sum(i.dependent for i in infos(a))

    return {"value": _round(coordinated / dep) if dep else None, "coordinated": coordinated,
            "dependent": dep}  # fmt: skip


@metric("clauses_per_sentence", scopes=SPAN_SCOPES, scalars=("value",))
def clauses_per_sentence(a: Analysis) -> dict[str, Any]:
    """Mean number of clauses in a sentence."""
    counts = [i.independent + i.dependent for i in infos(a)]

    return {"value": _round(statistics.fmean(counts)) if counts else None, "sentences": len(counts)}


@metric("mean_dependency_depth", scopes=SPAN_SCOPES, scalars=("value",))
def mean_dependency_depth(a: Analysis) -> dict[str, Any]:
    """Mean over sentences of the deepest parse-tree path. Catches nesting that length misses."""
    depths = [i.depth for i in infos(a)]

    return {"value": _round(statistics.fmean(depths)) if depths else None,
            "max": max(depths, default=None)}  # fmt: skip


# ---- variety and monotony -----------------------------------------------------------------


@metric("sentence_opener_distribution", scopes=SPAN_SCOPES, scalars=("distinct_share",))
def sentence_opener_distribution(a: Analysis) -> dict[str, Any]:
    """How sentences open (subject, prepositional phrase, ...) and how many distinct first words."""
    kinds = Counter(i.opener for i in infos(a))
    total = sum(kinds.values())
    firsts = {next((t.lower_ for t in i.span if t.is_alpha), "") for i in infos(a)}

    return {
        "counts": {k: kinds.get(k, 0) for k in OPENERS},
        "shares": {k: _round(kinds.get(k, 0) / total) if total else None for k in OPENERS},
        "distinct_share": _round(len(firsts) / total) if total else None,
        "sentences": total,
    }


@metric("paragraph_opener_repetition", scalars=("value",))
def paragraph_opener_repetition(a: Analysis) -> dict[str, Any]:
    """Share of consecutive paragraph pairs that open with the same construction or first word."""
    opened = []

    for group in a.paragraph_sentences():
        first = group[0]
        word = next((t.lemma_.lower() for t in first if t.is_alpha), "")
        opened.append((_opener(first), word))

    pairs = max(len(opened) - 1, 0)
    repeats = sum(
        1 for x, y in zip(opened, opened[1:], strict=False) if x[0] == y[0] or x[1] == y[1]
    )

    return {"value": _round(repeats / pairs) if pairs else None, "pairs": pairs, "repeats": repeats}


@metric("voice_distribution", scopes=SPAN_SCOPES, scalars=("passive_share",))
def voice_distribution(a: Analysis) -> dict[str, Any]:
    """Active and passive clauses. Passive means a passive subject with an auxiliary."""
    passive = sum(
        1
        for t in a.doc
        if t.dep_ == "nsubjpass" and any(c.dep_ == "auxpass" for c in t.head.children)
    )
    heads = sum(1 for c in a.clauses if c.head.pos_ in VERBAL)
    active = max(heads - passive, 0)
    total = active + passive

    return {"active": active, "passive": passive,
            "passive_share": _round(passive / total) if total else None}  # fmt: skip


# ---- style register -----------------------------------------------------------------------


@metric("modal_density", scopes=SPAN_SCOPES, scalars=("per_1k",))
def modal_density(a: Analysis) -> dict[str, Any]:
    """would, could, should, might, may and must per 1000 words. Grammatical hedging."""
    count = sum(1 for t in a.doc if t.tag_ == "MD" and t.lower_ in MODALS)

    return {"per_1k": _per_1k(count, a.words), "count": count}


@metric("nominal_verbal_ratio", scopes=SPAN_SCOPES, scalars=("value",))
def nominal_verbal_ratio(a: Analysis) -> dict[str, Any]:
    """Nouns per verb. High means the writing is built from nouns."""
    nouns = sum(1 for t in a.doc if t.pos_ in {"NOUN", "PROPN"})
    verbs = sum(1 for t in a.doc if t.pos_ == "VERB")

    return {"value": _round(nouns / verbs) if verbs else None, "nouns": nouns, "verbs": verbs}


def _tense(tok: Token) -> str | None:
    morph = tok.morph.to_dict()

    return morph.get("Tense") if morph.get("VerbForm") == "Fin" else None


@metric("tense_consistency", scalars=("shift_rate",))
def tense_consistency(a: Analysis) -> dict[str, Any]:
    """Tense shifts between consecutive finite clauses inside a paragraph."""
    shifts = pairs = 0

    for start, end in a.paragraphs:
        tenses = [t for c in a.clauses if start <= c.head.idx < end and (t := _tense(c.head))]
        pairs += max(len(tenses) - 1, 0)
        shifts += sum(1 for x, y in zip(tenses, tenses[1:], strict=False) if x != y)

    rate = _round(shifts / pairs) if pairs else None

    per_1k = _per_1k(shifts, a.words)

    return {"shifts": shifts, "pairs": pairs, "shift_rate": rate, "per_1k": per_1k}


@metric("hapax_ratio", scopes=SPAN_SCOPES, scalars=("value",))
def hapax_ratio(a: Analysis) -> dict[str, Any]:
    """Share of distinct lemmas that appear exactly once. Vocabulary churn."""
    counts = Counter(t.lemma_.lower() for t in a.doc if t.is_alpha)
    once = sum(1 for n in counts.values() if n == 1)

    return {"value": _round(once / len(counts)) if counts else None, "distinct": len(counts)}


def _antecedent(tok: Token) -> Token | None:
    word = tok.lower_

    for back in list(tok.doc[max(0, tok.i - LOOKBACK) : tok.i])[::-1]:
        if back.pos_ not in {"NOUN", "PROPN"}:
            continue

        plural = back.tag_ in {"NNS", "NNPS"}

        if word in SINGULAR_PRONOUNS and not plural:
            return back

        if word in PLURAL_PRONOUNS and plural:
            return back

        if word in PERSON_PRONOUNS and (back.pos_ == "PROPN" or back.ent_type_ == "PERSON"):
            return back

    return None


@metric("pronoun_antecedent_distance", scopes=SPAN_SCOPES, scalars=("mean",))
def pronoun_antecedent_distance(a: Analysis) -> dict[str, Any]:
    """Tokens from each anaphoric pronoun back to its nearest agreeing noun."""
    anaphors = SINGULAR_PRONOUNS | PLURAL_PRONOUNS | PERSON_PRONOUNS
    gaps, unresolved = [], 0

    for tok in a.doc:
        if tok.lower_ not in anaphors or tok.pos_ not in {"PRON", "DET"}:
            continue

        found = _antecedent(tok)

        if found is None:
            unresolved += 1
        else:
            gaps.append(tok.i - found.i)

    mean = _round(statistics.fmean(gaps)) if gaps else None

    return {"mean": mean, "max": max(gaps, default=None), "pronouns": len(gaps) + unresolved,
            "unresolved": unresolved}


# ---- document structure -------------------------------------------------------------------


@metric(
    "heading_hierarchy", needs_markdown=True, scalars=("skipped_levels", "single_child", "empty")
)
def heading_hierarchy(a: Analysis) -> dict[str, Any]:
    """Skipped heading levels, sections with one subsection, and headings with no body."""
    heads = a.model.headings
    issues: list[dict[str, Any]] = []
    skipped = single = empty = 0

    for i, h in enumerate(heads):
        previous = heads[i - 1].level if i else None

        if previous is not None and h.level > previous + 1:
            skipped += 1
            issues.append({"line": h.line, "kind": "skipped-level"})

        later = heads[i + 1 :]
        stop = next((n for n, x in enumerate(later) if x.level <= h.level), len(later))
        kids = [x for x in later[:stop] if x.level == h.level + 1]

        if len(kids) == 1:
            single += 1
            issues.append({"line": h.line, "kind": "single-child"})

        nxt = heads[i + 1].start if i + 1 < len(heads) else a.model.length
        body = a.raw[h.end : nxt].strip()

        if not body and not later[:stop]:
            empty += 1
            issues.append({"line": h.line, "kind": "empty"})

    return {"headings": len(heads), "skipped_levels": skipped, "single_child": single,
            "empty": empty, "issues": issues}  # fmt: skip


def _pos(tok: Token) -> str:
    return "VERB" if tok.pos_ in VERBAL else tok.pos_


@metric("list_parallelism", needs_markdown=True, scalars=("mismatched",))
def list_parallelism(a: Analysis) -> dict[str, Any]:
    """Lists whose items open with different parts of speech or use different verb forms."""
    issues = []

    for block in a.model.lists:
        spans = [a.doc.char_span(i.start, i.end, alignment_mode="expand") for i in block.items]
        rows = [s for s in spans if s is not None and len(s)]

        if len(rows) < 2:
            continue

        first = {_pos(next((t for t in s if not t.is_space), s[0])) for s in rows}
        forms = {FORMS.get(s.root.tag_, s.root.tag_) for s in rows if s.root.pos_ in VERBAL}

        if len(first) > 1 or len(forms) > 1:
            issues.append(
                {"line": block.line, "first_pos": sorted(first), "verb_forms": sorted(forms)}
            )

    return {"lists": len(a.model.lists), "mismatched": len(issues), "issues": issues}


@metric("code_prose_ratio", needs_markdown=True, scalars=("value",))
def code_prose_ratio(a: Analysis) -> dict[str, Any]:
    """Characters of code (fences and inline code) per character of prose."""
    fenced = sum(f.end - f.start for f in a.model.fences)
    code = fenced + a.model.inline_code_chars
    prose = max(a.model.length - fenced - a.model.inline_code_chars, 0)

    return {"value": _round(code / prose, 3) if prose else None, "code_chars": code,
            "prose_chars": prose}  # fmt: skip


@metric("link_density", needs_markdown=True, scalars=("per_1k",))
def link_density(a: Analysis) -> dict[str, Any]:
    """Links and bare URLs per 1000 words."""
    return {"per_1k": _per_1k(len(a.model.links), a.words), "links": len(a.model.links)}


@metric("sentence_overlap", scopes=("document",), scalars=("mean",))
def sentence_overlap(a: Analysis) -> dict[str, Any]:
    """Mean content-lemma Jaccard between each sentence and the one before it, per paragraph."""
    from clarity.overlap import overlap

    scores = []

    for group in a.paragraph_sentences():
        sets = [content_lemmas(s) for s in group]
        scores += [overlap(x, y) for x, y in zip(sets, sets[1:], strict=False)]

    return {"mean": _round(statistics.fmean(scores)) if scores else None, "pairs": len(scores)}
