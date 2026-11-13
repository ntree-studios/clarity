"""Structural backend: Python functions over the parsed doc."""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from nltk.corpus import wordnet as wn
from spacy.language import Language
from spacy.matcher import DependencyMatcher, Matcher
from spacy.tokens import Doc, Span, Token

from clarity.clauses import VERBAL, Clause, is_clause_head
from clarity.config import Rule
from clarity.matchers import phrase
from clarity.matchers.common import CharSpan, dedupe, sentences, token_span
from clarity.metrics import Analysis, scalar
from clarity.overlap import content_lemmas, overlap, paragraph_idf
from clarity.punct_model import score as punct_score
from clarity.punct_model import to_universal
from clarity.readability import count_syllables
from clarity.repeats import repeated_ngrams

PRONOUNS = {"it", "this", "that", "they", "he", "she", "we", "there"}
CONTRAST = {"but", "also", "rather", "instead", "yet", "whereas"}
CLAUSE_BREAK = {",", ";", ":", ".", "!", "?"}


@dataclass
class Context:
    nlp: Language
    sections: list[tuple[int, int]]
    # Optional per-hit detail appended to the rule message, keyed (rule id, start, end).
    details: dict[tuple[str, int, int], str] = field(default_factory=dict)
    clauses: list[Clause] = field(default_factory=list)
    clause_of: dict[int, int] = field(default_factory=dict)
    paragraphs: list[tuple[int, int]] = field(default_factory=list)
    analysis: Analysis | None = None


StructFn = Callable[[Doc, Rule, Context], list[CharSpan]]
REGISTRY: dict[str, StructFn] = {}


def register(fn: StructFn) -> StructFn:
    REGISTRY[fn.__name__] = fn

    return fn


def run(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    if rule.function not in REGISTRY:
        raise ValueError(f"rule {rule.id}: unknown structural function {rule.function!r}")

    return dedupe(REGISTRY[rule.function](doc, rule, ctx))


@register
def escalation_window(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """'not' + just/only within a few tokens, then a pivot (but, it, a comma) within the window."""
    then_within = int(rule.params.get("then_within", 3))
    window = int(rule.params.get("within", 12))
    pivots = set(rule.params.get("followed_by", ["but", "it", ","]))
    spans: list[CharSpan] = []

    for i in range(len(doc) - 1):
        if doc[i].lower_ not in {"not", "n't"}:
            continue

        mod = next((j for j in range(i + 1, min(i + 1 + then_within, len(doc)))
                    if doc[j].lower_ in {"just", "only"}), None)

        if mod is None:
            continue

        sent_end = doc[i].sent.end

        for j in range(mod + 1, min(mod + 1 + window, sent_end)):
            if doc[j].lower_ in pivots or doc[j].text in pivots:
                spans.append(token_span(doc, i, j + 1))

                break

    return spans


@register
def rule_of_three(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for tok in doc:
        conj = list(tok.conjuncts)

        if tok.dep_ == "conj" or len(conj) < 2:
            continue

        members = [tok, *conj]

        if rule.params.get("same_pos", False) and len({m.pos_ for m in members}) > 1:
            continue

        if len(members) < int(rule.params.get("chain_length", 3)):
            continue

        start = min(m.left_edge.i for m in members)
        end = max(m.right_edge.i for m in members) + 1
        spans.append(token_span(doc, start, end))

    return spans


def _is_markup_or_caption(sent: Span) -> bool:
    """Captions ('Figure 1.'), figures, markup and line-split artifacts are not fragments."""
    text = sent.text.strip()

    return any(c.isdigit() for c in text) or "*" in text or "\n" in text


@register
def consecutive_fragments(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    min_run = int(rule.params.get("min_run", 2))
    spans: list[CharSpan] = []
    run_: list[Span] = []

    def flush() -> None:
        if len(run_) >= min_run:
            span = (run_[0].start_char, run_[-1].end_char)
            spans.append(span)
            openers = {r[0].lower_ for r in run_}

            if rule.params.get("boost_on_shared_opener") and len(openers) == 1:
                opener = run_[0][0].text
                _detail(ctx, rule, span, f'{len(run_)} fragments share the opener "{opener}".')

        run_.clear()

    for sent in sentences(doc):
        if sent.root.pos_ in {"VERB", "AUX"} or _is_markup_or_caption(sent):
            flush()
        else:
            run_.append(sent)

    flush()

    return spans


@register
def question_answer(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    limit = float(rule.params.get("jaccard", 0.4))
    contained = bool(rule.params.get("containment", True))
    sents = sentences(doc)
    spans: list[CharSpan] = []

    for q, a in zip(sents, sents[1:], strict=False):
        if not q.text.rstrip().endswith("?"):
            continue

        asked, answered = content_lemmas(q), content_lemmas(a)
        # A short question restated whole in the answer ("What does that mean? It means ...")
        # scores low on Jaccard because the answer is longer, so containment also counts.
        restated = contained and bool(asked) and asked <= answered

        if overlap(asked, answered) > limit or restated:
            spans.append((q.start_char, a.end_char))

    return spans


def _section_sentences(doc: Doc, ctx: Context) -> list[list[Span]]:
    groups: list[list[Span]] = []

    for start, end in ctx.sections:
        group = [s for s in sentences(doc) if start <= s.start_char < end]

        if group:
            groups.append(group)

    return groups


@register
def section_restatement(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    limit = float(rule.params.get("jaccard", 0.5))
    minimum = int(rule.params.get("min_sentences", 3))
    spans: list[CharSpan] = []

    for group in _section_sentences(doc, ctx):
        if len(group) < minimum:
            continue

        first, last = group[0], group[-1]

        if overlap(content_lemmas(first), content_lemmas(last)) > limit:
            spans.append((last.start_char, last.end_char))

    return spans


def _paragraph_sentences(doc: Doc, ctx: Context) -> list[list[Span]]:
    """Sentences of each prose paragraph, in order. Paragraphs without a sentence are dropped."""
    sents = sentences(doc)
    groups: list[list[Span]] = []

    for start, end in ctx.paragraphs:
        group = [s for s in sents if start <= s.start_char < end]

        if group:
            groups.append(group)

    return groups


def _union(sets: list[set[str]]) -> set[str]:
    return set().union(*sets)


def _word_count(sent: Span) -> int:
    return sum(1 for t in sent if not t.is_punct and not t.is_space)


@register
def sentence_restatement(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """A sentence whose content lemmas mostly repeat one of the preceding sentences."""
    limit = float(rule.params.get("jaccard", 0.5))
    window = int(rule.params.get("window", 2))
    shorter = bool(rule.params.get("require_shorter_second", True))
    groups = _paragraph_sentences(doc, ctx)
    sets = [[content_lemmas(s) for s in group] for group in groups]
    weighted = bool(rule.params.get("idf_weighted", True))
    idf = paragraph_idf(_union(lemmas) for lemmas in sets) if weighted else None
    spans: list[CharSpan] = []

    for group, lemmas in zip(groups, sets, strict=True):
        for i in range(1, len(group)):
            for j in range(max(0, i - window), i):
                if shorter and _word_count(group[i]) >= _word_count(group[j]):
                    continue

                if overlap(lemmas[j], lemmas[i], idf) >= limit:
                    spans.append((group[i].start_char, group[i].end_char))

                    break

    return spans


def _introduces_subject(sent: Span, new: set[str]) -> bool:
    return any(t.dep_ in {"nsubj", "nsubjpass"} and t.lemma_.lower() in new for t in sent)


@register
def redundant_closer(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """A short last sentence that adds few content lemmas the paragraph has not already used."""
    max_words = int(rule.params.get("max_words", 15))
    max_new = int(rule.params.get("max_new_content_lemmas", 3))
    groups = _paragraph_sentences(doc, ctx)
    paragraph_lemmas = [_union([content_lemmas(s) for s in g]) for g in groups]
    spans: list[CharSpan] = []

    for i, group in enumerate(groups):
        if len(group) < 2:
            continue

        last = group[-1]
        mine = content_lemmas(last)
        new = mine - _union([content_lemmas(s) for s in group[:-1]])

        if not mine or len(new) > max_new or _word_count(last) > max_words:
            continue

        if last.text.rstrip().endswith(":"):  # introduces what follows; restates nothing
            continue

        leads_on = i + 1 < len(groups) and bool(new & paragraph_lemmas[i + 1])

        if rule.params.get("skip_new_subject", True) and _introduces_subject(last, new):
            continue

        if rule.params.get("skip_lead_in", True) and leads_on:
            continue

        spans.append((last.start_char, last.end_char))

    return spans


OPS = {"gt": lambda x, y: x > y, "gte": lambda x, y: x >= y, "lt": lambda x, y: x < y,
       "lte": lambda x, y: x <= y, "eq": lambda x, y: x == y}  # fmt: skip


def _line_span(doc: Doc, line: int) -> CharSpan:
    lines = doc.text.splitlines(keepends=True)
    start = sum(len(x) for x in lines[: line - 1])

    return start, start + len(lines[line - 1].rstrip("\r\n"))


def _holds(result: dict[str, Any], test: dict[str, Any]) -> bool:
    """True when the scalar named by test['key'] passes the first comparison it carries."""
    value = scalar(result, test["key"])
    op = next((o for o in OPS if o in test), None)

    return value is not None and op is not None and OPS[op](value, test[op])


@register
def metric_band(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """Fire when a registered metric crosses a threshold.

    params: metric, key (a dotted scalar of the result) and one of gt, gte, lt, lte, eq. Optional
    requires: {key, gte} gates on evidence size. With per_issue, one finding per entry of the
    result's issues list, placed on the entry's line.
    """
    if ctx.analysis is None:
        return []

    result = ctx.analysis.get(str(rule.params["metric"]))
    gate = rule.params.get("requires")

    if gate and not _holds(result, gate):
        return []

    if rule.params.get("per_issue"):
        return [_line_span(doc, int(i["line"])) for i in result.get("issues", [])]

    return _document_span(doc) if _holds(result, rule.params) else []


def _is_definition(sent: Span) -> bool:
    """'A X is a Y': a noun subject and a copula with a noun or verb complement."""
    root = sent.root

    if root.lemma_ != "be" or root.pos_ not in VERBAL:
        return False

    subject = next((c for c in root.children if c.dep_ == "nsubj"), None)

    return (
        subject is not None
        and subject.pos_ in {"NOUN", "PROPN"}
        and any(c.dep_ == "attr" for c in root.children)
    )


@register
def definition_chain(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """A paragraph that is mostly a run of definitions, which reads as a glossary and not as
    an explanation. Fires once per paragraph with min_definitions or more."""
    minimum = int(rule.params.get("min_definitions", 3))
    spans: list[CharSpan] = []

    for group in _paragraph_sentences(doc, ctx):
        found = [s for s in group if _is_definition(s)]

        if len(found) >= minimum:
            spans.append((found[0].start_char, found[-1].end_char))

    return spans


@register
def em_dash(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    chars = rule.params.get("chars", ["\u2014"])
    pattern = "[" + "".join(re.escape(c) for c in chars) + "]"

    return [(m.start(), m.end()) for m in re.finditer(pattern, doc.text)]


@register
def sentence_length_variance(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    minimum = int(rule.params.get("min_sentences", 5))
    floor = float(rule.params.get("min_stdev", 3.0))
    sents = sentences(doc)

    if len(sents) < minimum:
        return []

    lengths = [sum(1 for t in s if not t.is_punct and not t.is_space) for s in sents]

    if statistics.pstdev(lengths) >= floor:
        return []

    return [(sents[0].start_char, sents[0].end_char)]


@register
def stacked_adjectives(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """Runs of adjectives (commas and conjunctions allowed between) before a noun."""
    limit = int(rule.params.get("max_stack", 3))
    spans: list[CharSpan] = []
    run_: list[int] = []

    def close(noun: int) -> None:
        if len(run_) >= limit:
            spans.append(token_span(doc, run_[0], noun + 1))

        run_.clear()

    for tok in doc:
        if tok.pos_ == "ADJ":
            run_.append(tok.i)
        elif tok.text == "," or tok.pos_ == "CCONJ":
            continue
        elif tok.pos_ in {"NOUN", "PROPN"}:
            close(tok.i)
        else:
            run_.clear()

    return spans


@register
def hedge_stacking(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """Hedges per clause. Every hedge in a clause holding min_count or more is reported."""
    probe = Rule(id=rule.id, category=rule.category, phrases=list(rule.params["phrases"]))
    matcher = phrase.build_matcher(ctx.nlp, probe)
    by_clause: dict[int, list[CharSpan]] = {}

    for start, end in phrase.run(doc, probe, ctx.nlp, matcher):
        span = doc.char_span(start, end, alignment_mode="expand")

        if span is not None and span.start in ctx.clause_of:
            by_clause.setdefault(ctx.clause_of[span.start], []).append((start, end))

    need = int(rule.params.get("min_count", 2))

    return [hit for group in by_clause.values() if len(group) >= need for hit in group]


@register
def it_depends_final(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for group in _section_sentences(doc, ctx):
        last = group[-1]

        if last.text.strip().lower().startswith("it depends"):
            spans.append((last.start_char, last.end_char))

    return spans


def _is_word(tok: Token) -> bool:
    return not tok.is_punct and not tok.is_space


def _has_subject(tok: Token) -> bool:
    return is_clause_head(tok)


def _detail(ctx: Context, rule: Rule, span: CharSpan, text: str) -> None:
    ctx.details[(rule.id, span[0], span[1])] = text


def _document_span(doc: Doc) -> list[CharSpan]:
    sents = sentences(doc)

    return [(sents[0].start_char, sents[0].end_char)] if sents else []


@register
def long_sentence(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    limit = int(rule.params.get("max_words", 35))
    spans: list[CharSpan] = []

    for sent in sentences(doc):
        count = sum(1 for t in sent if _is_word(t))

        if count > limit:
            span = (sent.start_char, sent.end_char)
            spans.append(span)
            _detail(ctx, rule, span, f"{count} words, limit {limit}.")

    return spans


@lru_cache(maxsize=4096)
def verb_form(noun: str) -> str | None:
    """A verb derivationally related to the noun in WordNet, other than the noun itself."""
    for synset in wn.synsets(noun, pos=wn.NOUN):
        for lemma in synset.lemmas():
            if lemma.name().lower() != noun:
                continue

            for rel in lemma.derivationally_related_forms():
                name: str = str(rel.name()).lower()

                if rel.synset().pos() == "v" and name != noun:
                    return name

    return None


LIGHT_VERBS = {
    "make", "take", "give", "have", "conduct", "perform", "provide", "undertake", "carry",
    "reach", "come", "do", "hold", "offer", "issue", "render", "engage", "pay", "draw",
    "place", "put", "bring", "exercise", "raise",
}  # fmt: skip


def _light_verb_object(tok: Token) -> bool:
    """True for 'make a determination' and 'come to a conclusion'."""
    if tok.dep_ == "dobj":
        return tok.head.lemma_ in LIGHT_VERBS

    if tok.dep_ == "pobj" and tok.head.dep_ == "prep":
        return tok.head.head.lemma_ in LIGHT_VERBS

    return False


def _the_noun_of(tok: Token) -> bool:
    """True for 'the implementation of X'."""
    has_the = any(c.dep_ == "det" and c.lower_ == "the" for c in tok.children)
    has_of = any(c.dep_ == "prep" and c.lower_ == "of" for c in tok.children)

    return has_the and has_of


@register
def nominalization(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """A -tion/-ment/-ance/-ence/-ity/-ness noun with a verb form, in the wordy shapes only.

    Every such noun is not a defect: 'conversation' and 'intensity' are ordinary words. The
    wordy shapes are a light verb plus the noun ('make a determination') and 'the X of Y'.
    """
    suffixes = tuple(rule.params.get("suffixes", ["tion", "ment", "ance", "ence", "ity", "ness"]))
    spans: list[CharSpan] = []

    for tok in doc:
        word = tok.lemma_.lower()

        if tok.pos_ != "NOUN" or len(word) < 6 or not word.endswith(suffixes):
            continue

        if not (_light_verb_object(tok) or _the_noun_of(tok)):
            continue

        verb = verb_form(word)

        if verb:
            span = token_span(doc, tok.i, tok.i + 1)
            spans.append(span)
            _detail(ctx, rule, span, f'Try the verb "{verb}".')

    return spans


@register
def expletive_construction(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    spans: list[CharSpan] = []
    dep = DependencyMatcher(ctx.nlp.vocab)
    dep.add(
        "expl",
        [
            [
                {"RIGHT_ID": "v", "RIGHT_ATTRS": {"POS": {"IN": ["VERB", "AUX"]}}},
                {
                    "LEFT_ID": "v",
                    "REL_OP": ">",
                    "RIGHT_ID": "e",
                    "RIGHT_ATTRS": {"DEP": "expl", "LOWER": "there"},
                },
            ]
        ],
    )

    for _, ids in dep(doc):
        spans.append(token_span(doc, min(ids), max(ids) + 1))

    phrase_matcher = Matcher(ctx.nlp.vocab)
    phrase_matcher.add(
        "case",
        [[{"LEMMA": w} for w in ("it", "be", "the", "case", "that")]],
    )

    for _, start, end in phrase_matcher(doc):
        spans.append(token_span(doc, start, end))

    for i, tok in enumerate(doc[:-1]):
        if tok.lower_ != "what" or not (tok.is_sent_start or i == 0):
            continue

        for j in range(i + 1, min(i + 7, len(doc) - 1)):
            if doc[j].lemma_ == "do" and doc[j + 1].lemma_ == "be":
                spans.append(token_span(doc, i, j + 2))

                break

    return spans


def _ratio_outside(
    doc: Doc, rule: Rule, ctx: Context, value: float, low: float, high: float, label: str
) -> list[CharSpan]:
    if low <= value <= high:
        return []

    spans = _document_span(doc)

    if spans:
        _detail(ctx, rule, spans[0], f"{label} {value:.2f}, band {low} to {high}.")

    return spans


@register
def function_word_ratio(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    words = [t for t in doc if _is_word(t)]

    if len(words) < int(rule.params.get("min_words", 8)):
        return []

    fw = sum(1 for t in words if t.pos_ in {"DET", "ADP", "AUX", "CCONJ", "SCONJ", "PRON", "PART"})
    low, high = float(rule.params["min"]), float(rule.params["max"])

    return _ratio_outside(doc, rule, ctx, fw / len(words), low, high, "Function-word ratio")


@register
def syllables_per_word(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    words = [t for t in doc if t.is_alpha]

    if len(words) < int(rule.params.get("min_words", 8)):
        return []

    avg = sum(count_syllables(t.text) for t in words) / len(words)

    return _ratio_outside(doc, rule, ctx, avg, 0.0, float(rule.params["max"]), "Syllables per word")


@register
def adjective_density(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    words = [t for t in doc if _is_word(t)]
    nouns = sum(1 for t in words if t.pos_ == "NOUN")

    if len(words) < int(rule.params.get("min_words", 8)) or nouns == 0:
        return []

    ratio = sum(1 for t in words if t.pos_ == "ADJ") / nouns

    limit = float(rule.params["max_ratio"])

    return _ratio_outside(doc, rule, ctx, ratio, 0.0, limit, "Adjectives per noun")


@register
def intro_transition_comma(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    matcher = Matcher(ctx.nlp.vocab)
    openers = [phrase.compile_phrase(ctx.nlp, o, "lower") for o in rule.params["openers"]]
    matcher.add("opener", openers)
    best: dict[int, tuple[int, int]] = {}

    for _, start, end in matcher(doc):
        at_start = doc[start].is_sent_start or start == 0

        if at_start and (start not in best or end > best[start][1]):
            best[start] = (start, end)  # greedy longest match

    spans: list[CharSpan] = []

    for start, end in best.values():
        nxt = doc[end] if end < len(doc) else None

        if nxt is None or nxt.is_punct or nxt.is_space:
            continue

        first = doc[start].lower_

        if first == "however" and end == start + 1 and nxt.pos_ in {"ADJ", "ADV"}:
            continue  # "However hard he tried"

        if first == "instead" and nxt.lower_ == "of":
            continue

        spans.append(token_span(doc, start, end))

    return spans


@register
def lowercase_after_terminal(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for i, tok in enumerate(doc[:-1]):
        if tok.text not in {".", "!", "?"} or not tok.whitespace_ or i == 0:
            continue

        prev = doc[i - 1]

        if prev.like_num or prev.is_space or prev.lower_ in ABBREVIATIONS:
            continue  # list numbering such as "1. item", and "etc. had"

        j = i + 1

        while j < len(doc) and doc[j].is_space:
            j += 1

        if j < len(doc) and doc[j].is_alpha and doc[j].text[0].islower():
            spans.append(token_span(doc, j, j + 1))

    return spans


@register
def run_on_missing_comma(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for tok in doc:
        if tok.dep_ != "cc" or tok.lower_ not in {"and", "but", "or", "so", "yet", "nor"}:
            continue

        head = tok.head

        if head.pos_ not in {"VERB", "AUX"} or not _has_subject(head) or tok.i == 0:
            continue

        if doc[tok.i - 1].text == ",":
            continue

        conj = [c for c in head.children if c.dep_ == "conj" and c.i > tok.i]

        if any(c.pos_ in {"VERB", "AUX"} and _has_subject(c) for c in conj):
            spans.append(token_span(doc, tok.i, tok.i + 1))

    return spans


ABBREVIATIONS = {
    "etc", "vs", "cf", "approx", "inc", "ltd", "co", "dr", "mr", "mrs", "ms", "prof", "st", "no",
    "fig", "eq", "al", "jr", "sr", "e.g", "i.e",
}  # fmt: skip
REPORTING = {
    "say", "tell", "think", "believe", "know", "report", "claim", "argue", "suggest", "state",
    "explain", "ask", "note", "add", "reply", "mention", "insist", "admit", "hope", "feel",
    "show", "learn", "realize", "understand", "assume", "expect", "doubt", "wonder", "answer",
}  # fmt: skip
SUBORDINATORS = {
    "when", "while", "if", "although", "though", "because", "since", "once", "after", "before",
    "as", "unless", "whereas", "whenever", "until", "whilst", "wherever", "whether",
}  # fmt: skip
QUOTES = {'"', "\u201c", "\u201d"}


SPLICE_DEPS = {"conj", "ccomp", "parataxis"}


def _splice_pair(doc: Doc, comma: int) -> tuple[Token, Token] | None:
    """The (left, right) clause heads around a comma, or None.

    en_core_web_sm labels a splice either way round: the second clause hangs off the
    first, or the first hangs off the second as ccomp or parataxis.
    """
    for tok in doc:
        if tok.dep_ not in {"nsubj", "nsubjpass"} or tok.left_edge.i != comma + 1:
            continue

        right = tok.head

        if right.pos_ not in {"VERB", "AUX"}:
            continue

        left = right.head

        if right.dep_ in SPLICE_DEPS and left.i < comma and left.pos_ in {"VERB", "AUX"}:
            return left, right

        for child in right.children:
            if child.dep_ in SPLICE_DEPS and child.i < comma and child.right_edge.i == comma - 1:
                return child, right

    return None


@register
def comma_splice(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for tok in doc:
        if tok.text != ",":
            continue

        pair = _splice_pair(doc, tok.i)

        if pair is None:
            continue

        left, right = pair

        if not (_has_subject(left) and _has_subject(right)):
            continue

        if left.lemma_ in REPORTING or right.lemma_ in REPORTING:
            continue  # reporting verb taking a clausal complement

        start = min(left.left_edge.i, right.left_edge.i)
        end = max(left.right_edge.i, right.right_edge.i) + 1

        if any(t.text in QUOTES for t in doc[start:end]):
            continue  # split quotation

        if left.left_edge.lower_ in SUBORDINATORS:
            continue  # fronted subordinate clause, with or without a mark dependency

        spans.append(token_span(doc, tok.i, tok.i + 1))

    return spans


@register
def clause_overload(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """Finite clauses per sentence, from the shared clause utility, when commas are present."""
    limit = int(rule.params.get("max_heads", 4))
    min_commas = int(rule.params.get("min_commas", 1))
    by_sentence: dict[int, list[Clause]] = {}

    for clause in ctx.clauses:
        by_sentence.setdefault(clause.head.sent.start, []).append(clause)

    spans: list[CharSpan] = []

    for sent in sentences(doc):
        found = by_sentence.get(sent.start, [])
        commas = sum(1 for t in sent if t.text == ",")

        if len(found) > limit and commas >= min_commas:
            span = (sent.start_char, sent.end_char)
            verbs = ", ".join(c.head.text for c in found)
            spans.append(span)
            _detail(ctx, rule, span, f"{len(found)} clause heads: {verbs}.")

    return spans


@register
def rare_punctuation_context(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    floor = float(rule.params.get("threshold_per_10k", 10))
    spans: list[CharSpan] = []

    def tag(i: int, step: int) -> str:
        j = i + step

        while 0 <= j < len(doc) and doc[j].is_space:
            j += step

        if not 0 <= j < len(doc):
            return "BOS" if step < 0 else "EOS"

        return to_universal(doc[j].pos_, doc[j].tag_)

    for i, tok in enumerate(doc):
        if tok.text not in {",", ";", ":"}:
            continue

        prev, nxt = tag(i, -1), tag(i, 1)
        value = punct_score(tok.text, prev, nxt)

        if value < floor:
            span = token_span(doc, i, i + 1)
            spans.append(span)
            _detail(ctx, rule, span, f"{prev} {tok.text} {nxt} scores {value:.1f} per 10k.")

    return spans


COST_FORMS = {"cost", "costs", "costing"}
MONEY_WORDS = {
    "money", "dollar", "dollars", "euro", "euros", "pound", "pounds", "cent", "cents", "yen",
    "cash", "fee", "fees", "price", "prices", "penny", "pennies", "buck", "bucks", "usd", "eur",
    "gbp", "rupee", "rupees", "fortune", "salary", "wage", "wages", "bill", "bills",
}  # fmt: skip
AMOUNT_WORDS = {"a", "lot", "much", "little", "more", "less", "dearly", "plenty"}
OBJECT_STARTS = {"NOUN", "PROPN", "PRON", "NUM", "DET"}
CURRENCY = set("$\u20ac\u00a3\u00a5")


def _money_in_sentence(sent: Span) -> bool:
    return any(
        t.ent_type_ == "MONEY" or t.text in CURRENCY or t.lower_ in MONEY_WORDS for t in sent
    )


def _more_noun_than_verb(word: str) -> bool:
    return len(wn.synsets(word, pos=wn.NOUN)) > len(wn.synsets(word, pos=wn.VERB))


def _cost_object(doc: Doc, i: int) -> Token | None:
    """The first noun-like token after a cost verb, skipping determiners and modifiers."""
    for j in range(i + 1, min(i + 6, len(doc))):
        tok = doc[j]

        if tok.pos_ == "VERB" and doc[i].pos_ == "NOUN" and tok.tag_ in {"VB", "VBP"}:
            # spaCy reads "costs score" as a noun plus a verb. A closing word that is mostly a
            # noun (score, point) is the object; mostly a verb (fall, rise, vary) is a clause.
            closing = j + 1 >= len(doc) or doc[j + 1].is_punct

            return tok if closing and _more_noun_than_verb(tok.lemma_.lower()) else None

        if tok.is_punct or tok.pos_ in {"VERB", "ADP", "CCONJ", "SCONJ"}:
            return None

        if tok.pos_ in {"NOUN", "PROPN", "PRON", "NUM"}:
            return tok

    return None


@register
def figurative_cost(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """'cost' used as a figurative verb ('costs score', 'cost us credibility').

    Literal when the object is money, a price word or an amount, or the sentence names money.
    The noun ('the cost of', 'true costs', 'cost control') is never flagged.
    """
    spans: list[CharSpan] = []

    for i, tok in enumerate(doc):
        if tok.lower_ not in COST_FORMS or i + 1 >= len(doc):
            continue

        prev = doc[i - 1] if i else None

        if prev is not None and (
            prev.pos_ in {"DET", "ADP"} or (prev.pos_ == "ADJ" and tok.lower_ == "cost")
        ):
            continue  # "the cost of", "per cost", "total cost savings"

        if prev is not None and prev.text == "-" or doc[i + 1].text == "-":
            continue  # "cost-benefit"

        obj = _cost_object(doc, i)

        if obj is None or obj.lower_ in AMOUNT_WORDS | MONEY_WORDS or obj.like_num:
            continue

        if obj.pos_ == "NUM" or _money_in_sentence(tok.sent):
            continue

        if doc[i + 1].lower_ in {"of", "to", "per", "for", "centre", "center", "control"}:
            continue

        end = obj.i + 1
        span = token_span(doc, i, end)
        spans.append(span)
        advice = f'Say what happens: "lowers the {obj.lemma_}", "delays", "takes off".'
        _detail(ctx, rule, span, advice)

    return spans


@register
def repeated_ngram(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """A phrase the writer leans on: 3+ occurrences, spaced apart, with no proper nouns."""
    p = rule.params
    found = repeated_ngrams(
        doc,
        sizes=tuple(p.get("n", (2, 3, 4))),
        min_occurrences=int(p.get("min_occurrences", 3)),
        min_words_apart=int(p.get("min_words_apart", 40)),
        skip_pos=set(p.get("exclude_pos_only", [])) or None,
        exclude_proper_nouns=bool(p.get("exclude_proper_nouns", True)),
    )
    spans: list[CharSpan] = []

    for rep in found:
        for span in rep.spans:
            spans.append(span)
            _detail(ctx, rule, span, f'"{rep.phrase}" appears {len(rep.spans)} times.')

    return spans


def _passive_spans(doc: Doc, with_agent: bool) -> list[CharSpan]:
    spans: list[CharSpan] = []

    for tok in doc:
        if tok.dep_ != "nsubjpass" or not any(c.dep_ == "auxpass" for c in tok.head.children):
            continue

        agent = next((c for c in tok.head.children if c.dep_ == "agent"), None)

        if (agent is not None) != with_agent:
            continue

        end = (agent.right_edge.i if agent is not None else tok.head.i) + 1
        spans.append(token_span(doc, min(tok.left_edge.i, tok.head.i), end))

    return spans


@register
def passive_agentless(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """nsubjpass plus auxpass with no 'by' phrase: the actor is missing."""
    return _passive_spans(doc, with_agent=False)


@register
def passive_with_agent(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """nsubjpass plus auxpass with a 'by' phrase: the actor is named but placed last."""
    return _passive_spans(doc, with_agent=True)


@register
def adverb_propped_verb(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    weak = set(rule.params.get("weak_verbs", []))
    skip = {"only", "early", "daily", "likely", "family"}
    spans: list[CharSpan] = []

    for tok in doc:
        is_ly = tok.dep_ == "advmod" and tok.lower_.endswith("ly") and tok.lower_ not in skip

        if is_ly and tok.head.pos_ == "VERB" and tok.head.lemma_.lower() in weak:
            spans.append(token_span(doc, min(tok.i, tok.head.i), max(tok.i, tok.head.i) + 1))

    return spans


@register
def compound_chain(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """Runs of noun modifiers: 'quality score threshold'."""
    minimum = int(rule.params.get("min_length", 3))
    spans: list[CharSpan] = []
    i = 0

    while i < len(doc):
        j = i

        while (
            j < len(doc) - 1
            and doc[j].dep_ == "compound"
            and doc[j + 1].pos_ in {"NOUN", "PROPN"}
        ):
            j += 1

        if j - i + 1 >= minimum and doc[j].pos_ in {"NOUN", "PROPN"}:
            spans.append(token_span(doc, i, j + 1))

        i = max(j + 1, i + 1)

    return spans


def _prep_depth(prep: Token) -> int:
    best = 1

    for obj in prep.children:
        if obj.dep_ != "pobj":
            continue

        for nested in obj.children:
            if nested.dep_ == "prep":
                best = max(best, 1 + _prep_depth(nested))

    return best


@register
def nested_prep_depth(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """Sentences stacking prepositional phrases: of the X of the Y from the Z."""
    minimum = int(rule.params.get("min_depth", 4))
    spans: list[CharSpan] = []

    for sent in sentences(doc):
        depth = max((_prep_depth(t) for t in sent if t.dep_ == "prep"), default=0)

        if depth >= minimum:
            span = (sent.start_char, sent.end_char)
            spans.append(span)
            _detail(ctx, rule, span, f"{depth} prepositional phrases nested.")

    return spans


@register
def subj_verb_gap(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    """The reader holds the subject open while a long interruption passes."""
    limit = int(rule.params.get("max_tokens", 8))
    spans: list[CharSpan] = []

    for tok in doc:
        if tok.dep_ not in {"nsubj", "nsubjpass"} or tok.head.i <= tok.i:
            continue

        between = [t for t in doc[tok.i + 1 : tok.head.i] if not t.is_punct and not t.is_space]

        if len(between) > limit:
            span = token_span(doc, tok.i, tok.head.i + 1)
            spans.append(span)
            _detail(ctx, rule, span, f"{len(between)} words between subject and verb.")

    return spans


NEGATORS = {"no", "nobody", "nothing", "never", "none", "nowhere", "hardly", "scarcely"}


@register
def two_neg_in_clause(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    by_clause: dict[int, list[Token]] = {}

    for tok in doc:
        negates = tok.dep_ == "neg" or tok.lower_ in NEGATORS
        before_only = tok.i + 1 < len(doc) and doc[tok.i + 1].lower_ in {"only", "just"}

        if negates and not before_only and tok.i in ctx.clause_of:
            by_clause.setdefault(ctx.clause_of[tok.i], []).append(tok)

    flagged = [t for group in by_clause.values() if len(group) >= 2 for t in group]

    return [token_span(doc, t.i, t.i + 1) for t in flagged]
