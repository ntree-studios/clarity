"""Structural backend: Python functions over the parsed doc."""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from nltk.corpus import wordnet as wn
from spacy.language import Language
from spacy.matcher import DependencyMatcher, Matcher
from spacy.tokens import Doc, Span, Token

from clarity.config import Rule
from clarity.matchers import phrase
from clarity.matchers.common import CharSpan, dedupe, sentences, token_span
from clarity.punct_model import score as punct_score
from clarity.punct_model import to_universal
from clarity.readability import count_syllables

CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN"}
PRONOUNS = {"it", "this", "that", "they", "he", "she", "we", "there"}
CONTRAST = {"but", "also", "rather", "instead", "yet", "whereas"}
CLAUSE_BREAK = {",", ";", ":", ".", "!", "?"}


@dataclass
class Context:
    nlp: Language
    sections: list[tuple[int, int]]
    # Optional per-hit detail appended to the rule message, keyed (rule id, start, end).
    details: dict[tuple[str, int, int], str] = field(default_factory=dict)


StructFn = Callable[[Doc, Rule, Context], list[CharSpan]]
REGISTRY: dict[str, StructFn] = {}


def register(fn: StructFn) -> StructFn:
    REGISTRY[fn.__name__] = fn

    return fn


def run(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    if rule.function not in REGISTRY:
        raise ValueError(f"rule {rule.id}: unknown structural function {rule.function!r}")

    return dedupe(REGISTRY[rule.function](doc, rule, ctx))


def _content(sent: Span) -> set[str]:
    return {t.lemma_.lower() for t in sent if t.pos_ in CONTENT_POS and not t.is_stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


@register
def escalation_window(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    window = int(rule.params.get("window", 12))
    spans: list[CharSpan] = []

    for i in range(len(doc) - 1):
        if doc[i].lower_ not in {"not", "n't"} or doc[i + 1].lower_ not in {"just", "only"}:
            continue

        sent_end = doc[i].sent.end

        for j in range(i + 2, min(i + 2 + window, sent_end)):
            tok = doc[j]
            nxt = doc[j + 1] if j + 1 < len(doc) else None
            pivot = tok.lower_ in CONTRAST or (
                tok.text in {",", ";", ":"} and nxt is not None and nxt.lower_ in PRONOUNS
            )

            if pivot:
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
        start = min(m.left_edge.i for m in members)
        end = max(m.right_edge.i for m in members) + 1
        spans.append(token_span(doc, start, end))

    return spans


@register
def consecutive_fragments(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    min_run = int(rule.params.get("min_run", 2))
    spans: list[CharSpan] = []
    run_: list[Span] = []

    def flush() -> None:
        if len(run_) >= min_run:
            spans.append((run_[0].start_char, run_[-1].end_char))

        run_.clear()

    for sent in sentences(doc):
        if sent.root.pos_ in {"VERB", "AUX"}:
            flush()
        else:
            run_.append(sent)

    flush()

    return spans


@register
def question_answer(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    limit = float(rule.params.get("jaccard", 0.4))
    sents = sentences(doc)
    spans: list[CharSpan] = []

    for q, a in zip(sents, sents[1:], strict=False):
        if q.text.rstrip().endswith("?") and _jaccard(_content(q), _content(a)) > limit:
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

        if _jaccard(_content(first), _content(last)) > limit:
            spans.append((last.start_char, last.end_char))

    return spans


@register
def em_dash(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    return [(m.start(), m.end()) for m in re.finditer("—", doc.text)]


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


def _clause_ids(doc: Doc) -> list[int]:
    ids, current = [], 0

    for tok in doc:
        ids.append(current)

        if tok.text in CLAUSE_BREAK or tok.lower_ == "but":
            current += 1

    return ids


@register
def hedge_stacking(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    probe = Rule(id=rule.id, category=rule.category, phrases=list(rule.params["phrases"]))
    matcher = phrase.build_matcher(ctx.nlp, probe)
    hits = phrase.run(doc, probe, ctx.nlp, matcher)
    clauses = _clause_ids(doc)
    by_clause: dict[int, list[CharSpan]] = {}

    for start, end in hits:
        span = doc.char_span(start, end, alignment_mode="expand")

        if span is not None:
            by_clause.setdefault(clauses[span.start], []).append((start, end))

    return [(g[0][0], g[-1][1]) for g in by_clause.values() if len(g) >= 2]


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
    return any(c.dep_ in {"nsubj", "nsubjpass"} for c in tok.children)


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


@register
def nominalization(doc: Doc, rule: Rule, ctx: Context) -> list[CharSpan]:
    suffixes = tuple(rule.params.get("suffixes", ["tion", "ment", "ance", "ence", "ity", "ness"]))
    spans: list[CharSpan] = []

    for tok in doc:
        word = tok.lemma_.lower()

        if tok.pos_ != "NOUN" or len(word) < 6 or not word.endswith(suffixes):
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

        if prev.like_num or prev.is_space:
            continue  # list numbering such as "1. item"

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
    limit = int(rule.params.get("max_heads", 4))
    min_commas = int(rule.params.get("min_commas", 1))
    spans: list[CharSpan] = []

    for sent in sentences(doc):
        heads = {sent.root.i: sent.root}

        for tok in sent:
            finite_conj = tok.dep_ == "conj" and tok.pos_ in {"VERB", "AUX"} and _has_subject(tok)

            if tok.dep_ in {"advcl", "ccomp", "relcl", "xcomp"} or finite_conj:
                heads[tok.i] = tok

        commas = sum(1 for t in sent if t.text == ",")

        if len(heads) > limit and commas >= min_commas:
            span = (sent.start_char, sent.end_char)
            verbs = ", ".join(h.text for h in sorted(heads.values(), key=lambda t: t.i))
            spans.append(span)
            _detail(ctx, rule, span, f"{len(heads)} clause heads: {verbs}.")

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

        return to_universal(doc[j].pos_)

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
