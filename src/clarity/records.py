"""Record sets: what clarity measures, one record per unit, for rules written in YAML.

A record set is a named list of records. Each record covers a span of the source (start and end
offsets, and a line) and carries typed fields. A record set also has a summary: document-level
scalars that a rule's `requires` gate reads. The generic `query` structural function filters any
record set with conditions, so a new check is written in YAML over existing data, with no new
Python.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from clarity import topics
from clarity.composition import OPS as METRIC_OPS
from clarity.config import ConfigError, Rule
from clarity.metrics import Analysis, metric
from clarity.overlap import content_lemmas, overlap

SPAN_KEYS = ("start", "end")
MATCHES = ("all", "any")
AGGREGATES = ("count", "share")


def _contains(have: Any, want: Any) -> bool:
    if isinstance(have, str):
        return str(want).lower() in have.lower()

    return isinstance(have, list | tuple | set) and want in have


OPS: dict[str, Callable[[Any, Any], bool]] = {
    **METRIC_OPS, "ne": operator.ne,
    "in": lambda have, want: have in want, "not_in": lambda have, want: have not in want,
    "contains": _contains,
}  # fmt: skip


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    doc: str


@dataclass(frozen=True)
class RecordSet:
    name: str
    doc: str
    fields: tuple[Field, ...]
    summary: tuple[Field, ...]
    fn: Callable[[Analysis, dict[str, Any]], tuple[list[dict[str, Any]], dict[str, Any]]]


REGISTRY: dict[str, RecordSet] = {}


def _fields(spec: str) -> tuple[Field, ...]:
    """'name:type: meaning' lines, one per field."""
    out = []

    for line in filter(str.strip, spec.splitlines()):
        name, kind, doc = (part.strip() for part in line.split(":", 2))
        out.append(Field(name, kind, doc))

    return tuple(out)


def record_set(
    name: str, doc: str, fields: str, summary: str
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register fn(analysis, settings) -> (records, summary) as a record set."""

    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY[name] = RecordSet(name, doc, _fields(fields), _fields(summary), fn)

        return fn

    return wrap


def settings_for(
    analysis: Analysis, topic_override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The analysis settings, with a rule's params.topics layered over the topics block."""
    base = analysis.settings

    return {
        "topics": topics.effective(base.get("topics"), topic_override),
        "records": {**RECORD_DEFAULTS, **(base.get("records") or {})},
    }


def fetch(
    analysis: Analysis, name: str, topic_override: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Records and summary of one set, cached per effective settings."""
    if name not in REGISTRY:
        raise KeyError(f"unknown record set {name!r}; see clarity surface --records")

    settings = settings_for(analysis, topic_override)
    key = f"records:{name}:{topics.settings_key(settings)}"

    if key not in analysis._cache:
        analysis._cache[key] = REGISTRY[name].fn(analysis, settings)

    found: tuple[list[dict[str, Any]], dict[str, Any]] = analysis._cache[key]

    return found


def value(record: dict[str, Any], key: str) -> Any:
    """A field by dotted name: named.finance reads record['named']['finance']."""
    if key in record:
        return record[key]

    current: Any = record

    for part in key.split("."):
        current = current.get(part) if isinstance(current, dict) else None

    return current


def holds(record: dict[str, Any], cond: dict[str, Any]) -> bool:
    """One {field, op, value} condition, or {any: [...]} / {all: [...]} over a nested list.

    A missing value or a type mismatch does not hold (except for eq and ne, which compare None).
    """
    for group in MATCHES:
        if group in cond:
            return matches(record, cond[group], group)

    have = value(record, cond["field"])

    if have is None and cond["op"] not in ("eq", "ne"):
        return False

    try:
        return bool(OPS[cond["op"]](have, cond.get("value")))
    except TypeError:
        return False


def matches(record: dict[str, Any], where: list[dict[str, Any]], match: str = "all") -> bool:
    results = (holds(record, c) for c in where)

    return all(results) if match == "all" else any(results)


def first_failure(record: dict[str, Any], where: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((c for c in where if not holds(record, c)), None)


def shown(value_: Any) -> str:
    if isinstance(value_, float):
        return f"{value_:g}"

    if isinstance(value_, list | tuple):
        return ", ".join(shown(v) for v in value_)

    if isinstance(value_, dict):
        return "{" + ", ".join(f"{k}: {shown(v)}" for k, v in value_.items()) + "}"

    return str(value_)


_PLACEHOLDER = re.compile(r"\{([A-Za-z_][\w.]*)\}")


def fill(template: str, record: dict[str, Any]) -> str:
    """{field} placeholders replaced by the record's values."""
    return _PLACEHOLDER.sub(lambda m: shown(value(record, m.group(1))), template)


def describe(cond: dict[str, Any]) -> str:
    for group in MATCHES:
        if group in cond:
            return f"{group} of (" + "; ".join(describe(c) for c in cond[group]) + ")"

    return f"{cond['field']} {cond['op']} {shown(cond.get('value'))}"


# ---- validation ---------------------------------------------------------------------------


def _known_field(rs: RecordSet, name: str) -> bool:
    names = {f.name for f in rs.fields} | set(SPAN_KEYS) | {"line"}

    return name in names or any(name.startswith(f.name + ".") for f in rs.fields)


def _flatten(where: list[Any]) -> list[Any]:
    """Leaf conditions, with nested any/all groups opened up."""
    out: list[Any] = []

    for cond in where:
        group = next((cond[g] for g in MATCHES if isinstance(cond, dict) and g in cond), None)
        out += _flatten(group) if isinstance(group, list) else [cond]

    return out


def validate_params(rule: Rule) -> None:
    """A query rule's params, checked at load so a typo fails with the rule id."""
    p = rule.params
    name = p.get("records")

    def fail(message: str) -> None:
        raise ConfigError(f"rule {rule.id}: query {message}")

    if name not in REGISTRY:
        fail(f"records {name!r} is not a record set; known: {sorted(REGISTRY)}")

    rs = REGISTRY[str(name)]
    unknown = set(p) - {"records", "where", "match", "requires", "aggregate", "detail", "topics"}

    if unknown:
        fail(f"has unknown params {sorted(unknown)}")

    where = p.get("where") or []

    if not isinstance(where, list):
        fail("where must be a list of {field, op, value}")

    for cond in _flatten(where):
        if not isinstance(cond, dict) or set(cond) - {"field", "op", "value"}\
                or "field" not in cond:
            fail(f"condition {cond!r} must be {{field, op, value}} or {{any|all: [...]}}")

        if cond.get("op") not in OPS:
            fail(f"condition {cond!r}: op must be one of {list(OPS)}")

        if not _known_field(rs, cond["field"]):
            fields = [f.name for f in rs.fields]
            fail(f"{name} has no field {cond['field']!r}; fields: {fields}")

    if p.get("match", "all") not in MATCHES:
        fail(f"match must be one of {list(MATCHES)}")

    agg = p.get("aggregate")

    if agg is not None and (
        not isinstance(agg, dict) or agg.get("measure") not in AGGREGATES
        or agg.get("op") not in METRIC_OPS or not isinstance(agg.get("value"), int | float)
    ):  # fmt: skip
        fail(f"aggregate must be {{measure: count|share, op: {'|'.join(METRIC_OPS)}, value: N}}")

    gate = p.get("requires")

    if gate is not None:
        keys = {f.name for f in rs.summary}

        if not isinstance(gate, dict) or gate.get("key") not in keys:
            fail(f"requires must be {{key, <op>: value}} with key one of {sorted(keys)}")

    if p.get("topics") is not None:
        try:
            topics.validate(p["topics"], partial=True)
        except topics.TopicSettingsError as exc:
            fail(f"params.{exc}")


# ---- record sets: topics ------------------------------------------------------------------

TOPIC_SUMMARY = """
status: str: ok, too_short or no_shared_vocabulary; topic record sets are empty unless ok
anchor_score: float: word-weighted mean anchor alignment of all chunks; empty without an anchor
anchor_share_above: float: word share of chunks with anchor alignment >= align.on_topic_min
keyword_coverage: float: share of focus keywords found anywhere; empty without focus keywords
keyword_chunk_share: float: word share of chunks with a focus keyword
keyword_hits: int: focus keyword occurrences
n_chunks: int: chunks in the document
n_topics: int: topics detected
modularity: float: modularity of the topic partition
on_topic_share: float: word share on the main topic
unassigned_share: float: word share in no topic
drift_share: float: word share in drift runs
digression_count: int: digression runs
child_sections: int: sections below the root of a section tree; 0 for a plain string
"""


FOCUS_SCALARS = ("keyword_coverage", "keyword_chunk_share", "keyword_hits")
FOCUS_FIELDS = """
keyword_hits: int: focus keyword occurrences; absent without focus keywords
keyword_coverage: float: share of focus keywords found
keyword_chunk_share: float: word share of chunks with a focus keyword
missing_keywords: list: focus keywords not found
"""


def topic_summary(report: dict[str, Any]) -> dict[str, Any]:
    total = sum(c["words"] for c in report["chunks"]) or 1
    drift = sum(s["words"] for s in report["segments"] if s["kind"] == "drift")

    return {
        "status": report["status"], "n_chunks": report["n_chunks"],
        "n_topics": report["n_topics"], "modularity": report["modularity"],
        "on_topic_share": report["on_topic_share"],
        "unassigned_share": report["unassigned_share"],
        "drift_share": round(drift / total, 4) if report["status"] == "ok" else None,
        "digression_count": sum(1 for s in report["segments"] if s["kind"] == "digression"),
        "child_sections": report.get("child_sections", 0),
        "anchor_score": report["anchor_score"],
        "anchor_share_above": report["anchor_share_above"],
        **{k: report.get("focus", {}).get(k) for k in FOCUS_SCALARS},
    }  # fmt: skip


def _topic_result(analysis: Analysis, settings: dict[str, Any]) -> topics.Result:
    return topics.for_analysis(analysis, settings["topics"])


@metric("topic_structure", scalars=(
    "n_topics", "modularity", "on_topic_share", "unassigned_share", "drift_share",
    "digression_count", "anchor_score", "anchor_share_above", *FOCUS_SCALARS,
))  # fmt: skip
def topic_structure(analysis: Analysis) -> dict[str, Any]:
    """Topic count, modularity and shares from the chunk graph (see clarity topics)."""
    return topic_summary(_topic_result(analysis, settings_for(analysis)).report)


def _topic_set(
    name: str, doc: str, fields: str, rows: Callable[[topics.Result], list[dict[str, Any]]]
) -> None:
    def fn(analysis: Analysis, settings: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
        result = _topic_result(analysis, settings)
        ok = result.report["status"] == "ok"

        return (rows(result) if ok else []), topic_summary(result.report)

    record_set(name, doc, fields, TOPIC_SUMMARY)(fn)


def _span(result: topics.Result, first: int, last: int) -> dict[str, int]:
    return {"start": result.chunks[first].start, "end": result.chunks[last].end}


_topic_set(
    "topics.chunks", "one per chunk of the topic graph",
    """
    index: int: chunk number in text order
    topic: int: smoothed topic id; -1 is unassigned
    raw_topic: int: topic id before smoothing
    kind: str: main, digression or drift
    words: int: words in the chunk
    anchor_alignment: float: probability the walk from this chunk ends at the anchor
    aligned_to: str: the named topic this chunk aligns to, or none
    named: float: named.<name> is the probability of ending at that named topic
    terms: list: the chunk's top TF-IDF terms
    end_line: int: last line of the chunk
    keyword_hits: int: focus keyword occurrences; absent without focus keywords
    keywords_present: list: focus keywords found in the chunk
    """,
    lambda r: [dict(c) for c in r.report["chunks"]],
)
_topic_set(
    "topics.segments", "one per run of chunks with one topic, in text order",
    """
    kind: str: main, digression or drift
    topic: int: topic id of the run
    chunks: int: chunks in the run
    words: int: words in the run
    end_line: int: last line of the run
    terms: list: terms of the run's topic
    anchor_alignment: float: word-weighted mean anchor alignment of the run's chunks
    """,
    lambda r: [
        {**s, **_span(r, s["start"], s["end"]),
         "terms": next((t["terms"] for t in r.report["topics"] if t["id"] == s["topic"]), [])}
        for s in r.report["segments"]
    ],  # fmt: skip
)
_topic_set(
    "topics.topics", "one per detected topic, placed on its central chunk",
    """
    id: int: topic id; 0 has the most words
    share: float: word share of the text
    terms: list: class-based TF-IDF terms
    central_line: int: line of the most central chunk
    is_main: bool: the main topic
    anchor_alignment: float: word-weighted mean anchor alignment of the topic's chunks
    """,
    lambda r: [
        {**t, **_span(r, t["central_chunk"], t["central_chunk"]),
         "line": t["central_line"], "is_main": t["id"] == r.report["main_topic"]}
        for t in r.report["topics"]
    ],  # fmt: skip
)
_topic_set(
    "topics.sections", "one per titled section, measured against its own chunks",
    """
    heading: str: the section's title
    level: int: the section's depth plus one (the root is 1)
    heading_words: int: words in the title that are not stop words
    chunks: int: chunks in the section
    words: int: words in the section's chunks
    heading_alignment: float: mean probability the walk from its chunks ends at the heading
    anchor_alignment: float: word-weighted mean anchor alignment of the section's chunks
    main_topic_share: float: word share of the section on the document's main topic
    n_topics: int: topics present in the section
    section: str: the section's path
    parent_alignment: float: mean probability the walk from its chunks ends at its parent's text
    sibling_alignment: float: the same, toward the text of the sections beside it
    parent_gap: float: parent_alignment minus the median of its siblings'; negative is further
    sibling_similarity: float: mean TF-IDF cosine between its chunks and its siblings' chunks
    similarity_gap: float: sibling_similarity minus the median of its siblings'
    named: float: named.<name> is the word share of the section aligned to that named topic
    """ + FOCUS_FIELDS,
    lambda r: [dict(s) for s in r.report["sections"] if s["chunks"]],
)
_topic_set(
    "topics.nodes", "one per graph node (a chunk), with graph measures",
    """
    index: int: chunk number
    topic: int: smoothed topic id
    raw_topic: int: community before smoothing
    kind: str: main, digression or drift
    words: int: words in the chunk
    degree: int: number of edges
    weighted_degree: float: sum of edge weights
    within_topic_weight: float: edge weight to chunks of the same community
    between_topic_weight: float: edge weight to other communities
    betweenness: float: exact betweenness centrality over 1/weight distances
    closeness: float: closeness centrality over 1/weight distances
    is_central: bool: the most central chunk of its topic
    """,
    topics.node_records,
)
_topic_set(
    "topics.edges", "one per graph edge, placed from the first chunk to the second",
    """
    source: int: lower chunk index
    target: int: higher chunk index
    weight: float: total edge weight
    similarity: float: cosine similarity, 0 when the edge is adjacency only
    adjacent: bool: the chunks are consecutive
    kind: str: knn, adjacent or both
    same_topic: bool: both chunks are in one community
    """,
    topics.edge_records,
)


# ---- record sets: paragraphs and sections -------------------------------------------------

RECORD_DEFAULTS: dict[str, Any] = {
    "significance": [],
    "section_kinds": {},
}


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _words(span: Any) -> int:
    return sum(1 for t in span if not t.is_punct and not t.is_space)


@record_set(
    "paragraphs", "one per paragraph of a section's text (blank-line block; titles and items skip)",
    """
    index: int: paragraph number
    words: int: words in the paragraph
    sentences: int: sentences in the paragraph
    opener: str: first word, lower case
    first_sentence_overlap: float: content-lemma overlap of the first sentence with the rest
    half_overlap: float: content-lemma overlap of the first half of the sentences with the second
    ends_on_significance: bool: the last sentence uses a records.significance phrase
    has_numbers: bool: a number appears
    has_names: bool: a proper noun or named entity appears
    """,
    "count: int: prose paragraphs",
)
def paragraphs(analysis: Analysis, settings: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
    phrases = [p.lower() for p in settings["records"]["significance"]]
    out = []

    for i, group in enumerate(analysis.paragraph_sentences()):
        lemmas = [content_lemmas(s) for s in group]
        half = max(1, len(group) // 2)
        rest = set().union(*lemmas[1:]) if len(lemmas) > 1 else set()
        last = group[-1].text.lower()
        words = [t for s in group for t in s if not t.is_punct and not t.is_space]
        out.append({
            "index": i, "start": group[0].start_char, "end": group[-1].end_char,
            "line": _line(analysis.text, group[0].start_char),
            "words": len(words), "sentences": len(group),
            "opener": words[0].lower_ if words else "",
            "first_sentence_overlap": round(overlap(lemmas[0], rest), 4) if rest else None,
            "half_overlap": round(overlap(set().union(*lemmas[:half]),
                                          set().union(*lemmas[half:])), 4)
            if len(group) > 1 else None,
            "ends_on_significance": any(p in last for p in phrases),
            "has_numbers": any(t.like_num for t in words),
            "has_names": any(t.pos_ == "PROPN" or t.ent_type_ for t in words),
        })  # fmt: skip

    return out, {"count": len(out)}


@record_set(
    "sections", "one per titled section, with its own text and items as the body",
    """
    heading: str: the section's title
    level: int: the section's depth plus one (the root is 1)
    section: str: the section's path
    words: int: words in the body
    paragraphs: int: paragraphs in the body
    heading_overlap: float: share of the heading's content lemmas found in the body
    kind: str: the first records.section_kinds entry with a word in the heading, or other
    """,
    "count: int: titled sections",
)
def sections(analysis: Analysis, settings: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
    assert analysis.structure is not None
    kinds = settings["records"]["section_kinds"]
    out = []

    for p in analysis.structure.parts:
        heading = next((b for b in p.blocks if b.field == "title"), None)

        if heading is None or not p.title:
            continue

        start, end = (p.body[0].start, p.body[-1].end) if p.body else (heading.end, heading.end)
        head = analysis.doc.char_span(heading.start, heading.end, alignment_mode="expand")
        body = analysis.doc.char_span(start, end, alignment_mode="expand") if p.body else None
        head_lemmas = content_lemmas(head) if head is not None else set()
        body_lemmas = content_lemmas(body) if body is not None else set()
        title = p.title.lower()
        out.append({
            "heading": p.title, "level": p.depth + 1, "section": p.path,
            "start": heading.start, "end": end,
            "line": _line(analysis.text, heading.start),
            "words": _words(body) if body is not None else 0,
            "paragraphs": sum(1 for b in p.body if b.field == "text"),
            "heading_overlap": round(len(head_lemmas & body_lemmas) / len(head_lemmas), 4)
            if head_lemmas else None,
            "kind": next((k for k, words in kinds.items()
                          if any(re.search(rf"\b{re.escape(w.lower())}\b", title)
                                 for w in words)), "other"),
        })  # fmt: skip

    return out, {"count": len(out)}
