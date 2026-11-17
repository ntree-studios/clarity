"""Topics and topic shifts read off a similarity graph of chunks. No randomness, no model.

A port of the topicdrift.py proof of concept. The text is split into chunks, each chunk becomes a
TF-IDF vector, similar chunks are joined in a weighted graph, and greedy modularity communities
(Clauset-Newman-Moore) are the topics. Every answer is read off that graph: topic count, shares,
labels, alignment with named topics through an absorbing random walk, and runs of main topic,
digression and drift.

Determinism: similarities are rounded before any comparison, every sort breaks ties with
np.lexsort on a second key, graph nodes are integer chunk indexes, the input is NFC normalized
with Unix line endings, and nothing samples.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

from clarity.structure import Structure, from_text

UNITS = ("paragraph", "section", "sentences")
ANCHOR_SOURCES = ("none", "title", "first-heading")
DEFAULTS: dict[str, Any] = {
    "chunk": {"unit": "paragraph", "min_words": 25, "max_words": None, "min_count": 10},
    "vectorize": {
        "ngram_min": 1, "ngram_max": 2, "min_df": 2, "sublinear_tf": True,
        "stop_words": "english", "use_lemmas": False,
    },
    "graph": {
        "k": 6, "min_sim": 0.03, "adjacency": 0.1, "decimals": 10,
        "centrality": True, "measure_decimals": 6,
    },
    "communities": {"min_chunks": 2, "min_modularity": 0.2, "resolution": 1.0},
    "labels": {"top_n": 6},
    "smoothing": {"window": 3},
    "align": {"sink": 0.05, "boost": 3.0, "on_topic_min": 0.5},
    "anchor": "title",
    "named": {},
    "focus": {"keywords": [], "description": "", "named": {}},
}  # fmt: skip

# Each leaf: (type, minimum or None, maximum or None, one-line meaning). Used by validate() and
# by the surface docs.
SCHEMA: dict[str, dict[str, tuple[Any, ...]]] = {
    "chunk": {
        "unit": ("enum", UNITS, None, "what a chunk starts from: blank-line paragraphs, "
                 "markdown sections, or sentences"),
        "min_words": ("int", 1, None,
                      "short units merge forward until a chunk has this many words"),
        "max_words": ("int?", 1, None, "split a longer unit at sentence ends; null keeps it whole"),
        "min_count": ("int", 2, None, "fewer chunks than this: too short, no topics are reported"),
    },
    "vectorize": {
        "ngram_min": ("int", 1, None, "shortest n-gram counted"),
        "ngram_max": ("int", 1, None, "longest n-gram counted"),
        "min_df": ("int", 1, None, "drop terms found in fewer chunks than this"),
        "sublinear_tf": ("bool", None, None, "use 1 + log(tf) so repeats in one chunk count less"),
        "stop_words": ("str?", None, None, "stop-word list for scikit-learn: english, or null"),
        "use_lemmas": ("bool", None, None, "vectorize spaCy lemmas instead of surface words"),
    },
    "graph": {
        "k": ("int", 1, None, "each chunk links to its k most similar chunks"),
        "min_sim": ("float", 0.0, 1.0, "similarities below this make no edge"),
        "adjacency": ("float", 0.0, None, "extra weight between consecutive chunks"),
        "decimals": ("int", 1, 15, "similarities are rounded to this many places before compare"),
        "centrality": ("bool", None, None, "compute betweenness and closeness for graph nodes"),
        "measure_decimals": ("int", 1, 15, "rounding of published graph measures"),
    },
    "communities": {
        "min_chunks": ("int", 1, None, "a community smaller than this is unassigned (-1)"),
        "min_modularity": ("float", None, None, "below this modularity the text is one topic"),
        "resolution": ("float", 0.0, None, "above 1.0 gives more, smaller topics"),
    },
    "labels": {"top_n": ("int", 1, None, "terms kept per topic and per chunk")},
    "smoothing": {"window": ("int", 1, None, "majority-vote window over topic labels")},
    "align": {
        "sink": ("float", 0.0, None, "weight to the 'none of these' node; must be above 0"),
        "boost": ("float", 0.0, None, "multiplier on chunk-to-named-topic similarity"),
        "on_topic_min": ("float", 0.0, 1.0, "anchor alignment a chunk needs to count in "
                         "anchor_share_above (uncalibrated)"),
    },
}
TOP_KEYS = (*SCHEMA, "anchor", "named", "focus")
FOCUS_KEYS = ("keywords", "description", "named")


class TopicSettingsError(ValueError):
    """A topics setting has an unknown key, a wrong type or a value out of range."""


def merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Nested per-key merge: a group's keys replace one by one; named replaces per name."""
    out = copy.deepcopy(base)

    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **copy.deepcopy(value)}
        else:
            out[key] = copy.deepcopy(value)

    return out


def _check_leaf(path: str, value: Any, spec: tuple[Any, ...]) -> None:
    kind, low, high = spec[0], spec[1], spec[2]

    if kind == "enum":
        if value not in low:
            raise TopicSettingsError(f"{path} must be one of {list(low)}, got {value!r}")

        return

    if kind.endswith("?") and value is None:
        return

    base = kind.rstrip("?")
    ok = {
        "int": isinstance(value, int) and not isinstance(value, bool),
        "float": isinstance(value, int | float) and not isinstance(value, bool),
        "bool": isinstance(value, bool),
        "str": isinstance(value, str),
    }[base]

    if not ok:
        raise TopicSettingsError(f"{path} must be {base}, got {value!r}")

    if low is not None and value < low:
        raise TopicSettingsError(f"{path} must be >= {low}, got {value!r}")

    if high is not None and value > high:
        raise TopicSettingsError(f"{path} must be <= {high}, got {value!r}")


def validate(settings: dict[str, Any], partial: bool = False) -> None:
    """Refuse unknown keys, wrong types and out-of-range values. partial allows missing keys."""
    if not isinstance(settings, dict):
        raise TopicSettingsError("topics must be a mapping")

    unknown = set(settings) - set(TOP_KEYS)

    if unknown:
        raise TopicSettingsError(f"topics: unknown keys {sorted(unknown)}; known: {list(TOP_KEYS)}")

    for group, leaves in SCHEMA.items():
        if group not in settings:
            if not partial:
                raise TopicSettingsError(f"topics.{group} is missing")

            continue

        block = settings[group]

        if not isinstance(block, dict):
            raise TopicSettingsError(f"topics.{group} must be a mapping")

        extra = set(block) - set(leaves)

        if extra:
            raise TopicSettingsError(
                f"topics.{group}: unknown keys {sorted(extra)}; known: {list(leaves)}"
            )

        for leaf, spec in leaves.items():
            if leaf in block:
                _check_leaf(f"topics.{group}.{leaf}", block[leaf], spec)
            elif not partial:
                raise TopicSettingsError(f"topics.{group}.{leaf} is missing")

    if "anchor" in settings and not isinstance(settings["anchor"], str):
        raise TopicSettingsError(
            f"topics.anchor must be text or one of {list(ANCHOR_SOURCES)}, "
            f"got {settings['anchor']!r}"
        )

    named = settings.get("named", {})

    if not isinstance(named, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in named.items()
    ):
        raise TopicSettingsError("topics.named must map each name to a non-empty description")

    if "none" in named:
        raise TopicSettingsError("topics.named: 'none' is reserved for the sink")

    _validate_focus(settings.get("focus", {}))

    vec = settings.get("vectorize", {})

    if vec.get("ngram_min", 1) > vec.get("ngram_max", 2):
        raise TopicSettingsError("topics.vectorize.ngram_min must be <= ngram_max")

    if settings.get("align", {}).get("sink", 1.0) <= 0:
        raise TopicSettingsError("topics.align.sink must be above 0")

    max_words = settings.get("chunk", {}).get("max_words")

    if max_words is not None and max_words < settings.get("chunk", {}).get("min_words", 1):
        raise TopicSettingsError("topics.chunk.max_words must be >= min_words")


def _validate_focus(focus: Any) -> None:
    def words(value: Any) -> bool:
        return isinstance(value, list) and all(isinstance(w, str) and w.strip() for w in value)

    if not isinstance(focus, dict) or set(focus) - set(FOCUS_KEYS):
        raise TopicSettingsError(f"topics.focus must be a mapping of {list(FOCUS_KEYS)}")

    if "keywords" in focus and not words(focus["keywords"]):
        raise TopicSettingsError("topics.focus.keywords must be a list of words or phrases")

    if not isinstance(focus.get("description", ""), str):
        raise TopicSettingsError("topics.focus.description must be text")

    for name, entry in (focus.get("named") or {}).items():
        if not isinstance(entry, dict) or set(entry) - {"keywords", "description"} or (
            "keywords" in entry and not words(entry["keywords"])
        ):
            raise TopicSettingsError(
                f"topics.focus.named.{name} must be {{keywords: [...], description: text}}"
            )


def focus_text(entry: dict[str, Any]) -> str:
    """Description and keywords as one text, for alignment."""
    return " ".join([entry.get("description") or "", *(entry.get("keywords") or [])]).strip()


def focus_terms(focus: dict[str, Any]) -> list[str]:
    """Every focus keyword, including those of focus.named entries, in order, once each."""
    found = [*focus.get("keywords", []),
             *[k for e in (focus.get("named") or {}).values() for k in e.get("keywords") or []]]

    return list(dict.fromkeys(found))  # fmt: skip


def effective(*layers: dict[str, Any] | None) -> dict[str, Any]:
    """DEFAULTS merged with each layer in order, validated."""
    out = DEFAULTS

    for layer in layers:
        if layer:
            validate(layer, partial=True)
            out = merge(out, layer)

    validate(out)

    return out


def settings_key(settings: dict[str, Any]) -> str:
    return "topics:" + json.dumps(settings, sort_keys=True)


# ---------- 0. normalize ----------
def normalize(text: str) -> str:
    """NFC and Unix line endings, applied before chunking."""
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


# ---------- 1. chunk ----------
@dataclass
class Chunk:
    index: int
    start: int
    end: int
    text: str
    words: int


_SENT_END = re.compile(r"(?<=[.!?])\s+")


def _trim(text: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Ranges with surrounding whitespace removed; empty ones dropped."""
    out = []

    for a, b in ranges:
        piece = text[a:b]

        if piece.strip():
            lead, trail = len(piece) - len(piece.lstrip()), len(piece) - len(piece.rstrip())
            out.append((a + lead, b - trail))

    return out


def _paragraphs(text: str, lo: int = 0, hi: int | None = None) -> list[tuple[int, int]]:
    hi = len(text) if hi is None else hi

    return _trim(text, _clip(from_text(text).body_blocks(), lo, hi))


def _clip(ranges: list[tuple[int, int]], lo: int, hi: int) -> list[tuple[int, int]]:
    return [(max(a, lo), min(b, hi)) for a, b in ranges if a < hi and b > lo]


def _units(
    text: str, unit: str, structure: Structure, sentences: list[tuple[int, int]] | None
) -> list[tuple[int, int]]:
    if unit == "paragraph":
        return _trim(text, structure.body_blocks())

    if unit == "section":
        return _trim(text, structure.sections())

    return _sentence_ranges(text, sentences, 0, len(text))


def _sentence_ranges(
    text: str, sentences: list[tuple[int, int]] | None, lo: int, hi: int
) -> list[tuple[int, int]]:
    """spaCy sentence ranges clipped to [lo, hi), or a punctuation split when there is no parse."""
    if sentences is None:
        sentences = []

        for a, b in _paragraphs(text, lo, hi):
            cuts = [a, *[m.end() for m in _SENT_END.finditer(text, a, b)], b]
            sentences += list(zip(cuts, cuts[1:], strict=False))

    return _trim(text, _clip(sentences, lo, hi))


def _split_long(
    text: str, units: list[tuple[int, int]], max_words: int, sentences: list[tuple[int, int]] | None
) -> list[tuple[int, int]]:
    """Units over max_words split at sentence ends. One sentence over the limit stays whole."""
    out: list[tuple[int, int]] = []

    for lo, hi in units:
        if len(text[lo:hi].split()) <= max_words:
            out.append((lo, hi))

            continue

        group: list[tuple[int, int]] = []

        for s in _sentence_ranges(text, sentences, lo, hi):
            if group and len(text[group[0][0] : s[1]].split()) > max_words:
                out.append((group[0][0], group[-1][1]))
                group = []

            group.append(s)

        if group:
            out.append((group[0][0], group[-1][1]))

    return out


def chunk_text(
    text: str,
    min_words: int = 25,
    unit: str = "paragraph",
    max_words: int | None = None,
    structure: Structure | None = None,
    sentences: list[tuple[int, int]] | None = None,
) -> list[Chunk]:
    """Split into units, merging short units into the next one (topicdrift.chunk_text).

    Each chunk keeps its character range in text, so findings map back to lines. In a section
    tree a chunk never spans two sections: a short last unit of a section is its own chunk.
    """
    structure = structure or from_text(text)
    units = _units(text, unit, structure, sentences)

    if max_words is not None:
        units = _split_long(text, units, max_words, sentences)

    spans: list[list[tuple[int, int]]] = []
    buf: list[tuple[int, int]] = []

    for u in units:
        if buf and structure.tree and structure.part_at(u[0]) != structure.part_at(buf[0][0]):
            spans.append(buf)
            buf = []

        buf.append(u)

        if sum(len(text[a:b].split()) for a, b in buf) >= min_words:
            spans.append(buf)
            buf = []

    if buf:
        same = spans and structure.part_at(spans[-1][0][0]) == structure.part_at(buf[0][0])

        if spans and (same or not structure.tree):
            spans[-1].extend(buf)
        else:
            spans.append(buf)

    chunks = []

    for i, group in enumerate(spans):
        body = normalize(" ".join(" ".join(text[a:b].split()) for a, b in group))
        chunks.append(Chunk(i, group[0][0], group[-1][1], body, len(body.split())))

    return chunks


# ---------- 2. vectorize ----------
def vectorize(
    docs: list[str], cfg: dict[str, Any], forced: list[str] | None = None
) -> tuple[TfidfVectorizer, Any]:
    """TF-IDF with unit-length rows, so a dot product is cosine similarity.

    forced are focus keywords: after the fit with min_df, their n-grams (as the vectorizer's own
    analyzer splits them) join the vocabulary, so a keyword in fewer than min_df chunks, or in
    none, is not dropped. With no forced terms this is the plain fit.
    """
    options = {
        "stop_words": cfg["stop_words"], "sublinear_tf": cfg["sublinear_tf"],
        "ngram_range": (cfg["ngram_min"], cfg["ngram_max"]),
    }  # fmt: skip
    vec = TfidfVectorizer(min_df=cfg["min_df"], **options)
    X = vec.fit_transform(docs)
    analyzer = vec.build_analyzer()
    extra = {g for term in forced or [] for g in analyzer(term)} - set(vec.vocabulary_)

    if not extra:
        return vec, X

    vec = TfidfVectorizer(vocabulary=sorted(set(vec.vocabulary_) | extra), **options)

    return vec, vec.fit_transform(docs)


# ---------- 3. graph ----------
def similarity(X: Any, decimals: int = 10) -> np.ndarray:
    S: np.ndarray = np.round((X @ X.T).toarray(), decimals)  # rounding absorbs float noise
    np.fill_diagonal(S, 0.0)

    return S


def build_graph(
    S: np.ndarray, k: int = 6, min_sim: float = 0.03, adjacency: float = 0.1
) -> tuple[np.ndarray, np.ndarray]:
    """Union k-nearest-neighbor graph plus a small weight between consecutive chunks.

    Returns the symmetric weight matrix and the kNN part alone.
    """
    n = S.shape[0]
    W = np.zeros_like(S)
    idx = np.arange(n)

    for i in range(n):
        order = np.lexsort((idx, -S[i]))  # similarity desc, index asc

        for j in order[:k]:
            if S[i, j] >= min_sim:
                W[i, j] = S[i, j]

    knn = np.maximum(W, W.T)
    W = knn.copy()

    for i in range(n - 1):  # text order is evidence too
        W[i, i + 1] += adjacency
        W[i + 1, i] += adjacency

    return W, knn


# ---------- 4. topics ----------
def detect_topics(
    W: np.ndarray,
    words: list[int],
    min_chunks: int = 2,
    min_modularity: float = 0.2,
    resolution: float = 1.0,
) -> tuple[np.ndarray, float]:
    """Greedy modularity communities. Returns (labels, modularity).

    Topic ids are ordered by word share, largest first. -1 marks chunks in communities smaller
    than min_chunks. If modularity is below min_modularity the text is one topic.
    """
    n = W.shape[0]

    if n < 2 or not W.any():
        return np.zeros(n, dtype=int), 0.0

    G = nx.from_numpy_array(W)  # integer node ids
    comms = nx.community.greedy_modularity_communities(G, weight="weight", resolution=resolution)
    q = nx.community.modularity(G, comms, weight="weight")

    if q < min_modularity:
        return np.zeros(n, dtype=int), float(q)

    kept = [sorted(c) for c in comms if len(c) >= min_chunks]
    kept.sort(key=lambda c: (-sum(words[i] for i in c), c[0]))
    labels = np.full(n, -1)

    for t, c in enumerate(kept):
        labels[c] = t

    return labels, float(q)


# ---------- 5. label ----------
def label_topics(
    docs: list[str], labels: np.ndarray, W: np.ndarray, top_n: int = 6, stop_words: Any = "english"
) -> dict[int, dict[str, Any]]:
    """Class-based TF-IDF terms and the most central chunk per topic."""
    topics = sorted(t for t in set(labels.tolist()) if t >= 0)

    if not topics:
        return {}

    joined = [" ".join(docs[i] for i in np.where(labels == t)[0]) for t in topics]

    try:
        cv = CountVectorizer(stop_words=stop_words)
        C = cv.fit_transform(joined).toarray().astype(float)
        terms = cv.get_feature_names_out()
        tf = C / np.maximum(C.sum(axis=1, keepdims=True), 1.0)
        idf = np.log(1.0 + C.sum(axis=1).mean() / C.sum(axis=0))
        score = np.round(tf * idf, 12)
    except ValueError:  # every word is a stop word
        terms, score = np.array([], dtype=str), np.zeros((len(topics), 0))

    out = {}

    for row, t in enumerate(topics):
        order = np.lexsort((terms, -score[row]))  # score desc, term asc
        members = np.where(labels == t)[0]
        inner = W[np.ix_(members, members)].sum(axis=1)
        central = int(members[np.lexsort((members, -inner))[0]])
        out[t] = {"terms": [str(terms[j]) for j in order[:top_n]], "central_chunk": central}

    return out


def shares(labels: np.ndarray, words: list[int]) -> dict[int, float]:
    """Word-weighted share of the text per topic id (-1 = unassigned)."""
    total = float(sum(words)) or 1.0
    agg: Counter[int] = Counter()

    for lab, w in zip(labels.tolist(), words, strict=True):
        agg[lab] += w

    return {t: agg[t] / total for t in sorted(agg, key=lambda t: (t < 0, t))}


# ---------- 6. alignment with named topics ----------
def align(
    vec: TfidfVectorizer, X: Any, W: np.ndarray, named: dict[str, str], sink: float = 0.05,
    boost: float = 3.0,
) -> tuple[list[str], np.ndarray]:  # fmt: skip
    """Absorbing random walk from each chunk to named topics or a sink.

    Returns names + ["none"] and an (n_chunks, n_named + 1) matrix of absorption probabilities.
    """
    names = list(named)
    Qv = vec.transform([named[k] for k in names])
    C = np.clip(np.round((X @ Qv.T).toarray(), 10), 0.0, None) * boost
    n = W.shape[0]
    R = np.hstack([C, np.full((n, 1), sink)])
    rowsum = W.sum(axis=1, keepdims=True) + R.sum(axis=1, keepdims=True)
    B = np.linalg.solve(np.eye(n) - W / rowsum, R / rowsum)

    return [*names, "none"], B


def aligned_shares(names: list[str], B: np.ndarray, words: list[int]) -> dict[str, float]:
    """Word-weighted share of chunks whose most likely absorber is each name."""
    total = float(sum(words)) or 1.0
    best = B.argmax(axis=1)  # ties resolve to first name

    return {
        nm: sum(w for b, w in zip(best, words, strict=True) if b == j) / total
        for j, nm in enumerate(names)
    }


# ---------- 7. topic shifts ----------
def smooth_labels(labels: np.ndarray, window: int = 3) -> np.ndarray:
    """Sliding majority vote. Ties keep the chunk's own label."""
    half = window // 2
    out = labels.copy()

    for i in range(len(labels)):
        seg = labels[max(0, i - half) : i + half + 1].tolist()
        counts = Counter(seg)
        top = max(counts.values())
        winners = sorted(t for t, c in counts.items() if c == top)
        out[i] = labels[i] if labels[i] in winners else winners[0]

    return out


def segment(labels: np.ndarray, main: int) -> list[dict[str, Any]]:
    """Run-length encode labels and classify each run against the main topic."""
    runs: list[dict[str, Any]] = []
    start = 0

    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs.append({"start": start, "end": i - 1, "topic": int(labels[start])})
            start = i

    for r_i, r in enumerate(runs):
        if r["topic"] == main:
            r["kind"] = "main"
        elif any(later["topic"] == main for later in runs[r_i + 1 :]):
            r["kind"] = "digression"
        else:
            r["kind"] = "drift"

    return runs


# ---------- pipeline ----------
def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _where(text: str, structure: Structure | None, start: int, end: int) -> dict[str, Any]:
    """Where a span is, as findings report it. The result has the section path, the field, and
    the first and last line counted inside that field. Without a structure the lines count from
    the start of the text."""
    if structure is None:
        return {"section": "", "field": "", "line": _line(text, start),
                "end_line": _line(text, end)}  # fmt: skip

    first = structure.locate(start, start)
    last = structure.locate(max(start, end - 1), max(start, end - 1))

    return {"section": structure.parts[structure.part_at(start)].path, "field": first["field"],
            "line": first["line"], "end_line": last["line"]}  # fmt: skip


def headings(structure: Structure) -> list[tuple[int, int, str]]:
    """(level, offset, title) of each part title, in tree order."""
    return [(level, start, title) for level, start, _, title in structure.headings()]


def anchor_text(source: str, structure: Structure) -> str | None:
    """The anchor a setting names: none; title (the root part's title, else the first part
    title); first-heading (the first part title); or literal text. None when there is no title."""
    if source == "none":
        return None

    found = headings(structure)

    if source == "title":
        return next((t for level, _, t in found if level == 1), found[0][2] if found else None)

    if source == "first-heading":
        return found[0][2] if found else None

    return source


@dataclass
class Result:
    """The report plus the objects records and exports are read from."""

    report: dict[str, Any]
    graph: nx.Graph
    chunks: list[Chunk]


TOO_SHORT, NO_SHARED = "too_short", "no_shared_vocabulary"
STATUS_DOCS = {
    "ok": "topics were detected",
    TOO_SHORT: "fewer chunks than chunk.min_count: too short for topic analysis",
    NO_SHARED: "no term occurs in vectorize.min_df chunks, so no chunk links to another",
}


def _not_analyzed(
    chunks: list[Chunk], text: str, settings: dict[str, Any], status: str,
    hits: list[Counter[str]] | None,
) -> Result:  # fmt: skip
    """The guard around the algorithm: no topics, no segments, every chunk unassigned."""
    labels = np.full(len(chunks), -1)
    W = np.zeros((len(chunks), len(chunks)))

    return _assemble(text, chunks, [c.words for c in chunks], labels, labels, 0.0, -1, W, W, {},
                     None, None, settings, status, hits=hits)  # fmt: skip


def analyze(
    text: str,
    settings: dict[str, Any] | None = None,
    *,
    structure: Structure | None = None,
    sentences: list[tuple[int, int]] | None = None,
    lemmas: list[str] | None = None,
    doc: Any = None,
) -> Result:
    """The full topic report for text.

    text is what is chunked; structure is the section tree it was rendered from (section titles
    are the headings), a plain-text structure when None. sentences are sentence character ranges
    for unit: sentences and max_words. lemmas, one string per chunk, are required by use_lemmas.
    doc, a spaCy parse of text, lets focus keywords match on lemmas as well as surface forms.
    """
    cfg = effective(settings) if settings is not None else effective()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if structure is None or structure.text != text:
        structure = from_text(text)

    ch = cfg["chunk"]
    chunks = chunk_text(text, ch["min_words"], ch["unit"], ch["max_words"], structure, sentences)

    focus = cfg["focus"]
    hits = keyword_counts(text, chunks, focus_terms(focus), doc) if focus_terms(focus) else None

    if len(chunks) < max(2, ch["min_count"]):
        return _not_analyzed(chunks, text, cfg, TOO_SHORT, hits)

    docs = [c.text for c in chunks]

    if cfg["vectorize"]["use_lemmas"]:
        if lemmas is None:
            raise ValueError("topics.vectorize.use_lemmas needs the spaCy parse")

        docs = [normalize(d) for d in lemmas]

    words = [c.words for c in chunks]

    try:
        vec, X = vectorize(docs, cfg["vectorize"], focus_terms(focus))
    except ValueError:  # no term occurs in min_df chunks
        return _not_analyzed(chunks, text, cfg, NO_SHARED, hits)

    g = cfg["graph"]
    S = similarity(X, g["decimals"])
    W, knn = build_graph(S, g["k"], g["min_sim"], g["adjacency"])
    c = cfg["communities"]
    labels, Q = detect_topics(W, words, c["min_chunks"], c["min_modularity"], c["resolution"])
    info = label_topics(docs, labels, W, cfg["labels"]["top_n"], cfg["vectorize"]["stop_words"])
    a = cfg["align"]
    found = (anchor_text(cfg["anchor"], structure), focus_text(focus))
    anchor = " ".join(t for t in found if t) or None
    anchor_b = None

    if anchor:  # main topic = closest to anchor
        _, anchor_b = align(vec, X, W, {"anchor": anchor}, a["sink"], a["boost"])
        topics = sorted(info)
        mass = [anchor_b[labels == t, 0].mean() for t in topics]
        main = topics[int(np.argmax(np.round(mass, 10)))] if topics else 0
    else:  # main topic = largest
        main = 0

    smoothed = smooth_labels(labels, cfg["smoothing"]["window"])
    named_b = None

    named = {**cfg["named"], **{n: focus_text(e) for n, e in focus["named"].items()}}

    if named:
        named_b = align(vec, X, W, named, a["sink"], a["boost"])

    return _assemble(text, chunks, words, labels, smoothed, Q, main, W, knn, info, anchor_b,
                     named_b, cfg, "ok", structure=structure, anchor=anchor,
                     chunk_terms=_chunk_terms(vec, X, cfg["labels"]["top_n"]),
                     vec=vec, X=X, hits=hits)  # fmt: skip


def _chunk_terms(vec: TfidfVectorizer, X: Any, top_n: int) -> list[list[str]]:
    terms = vec.get_feature_names_out()
    dense = np.round(X.toarray(), 10)
    out = []

    for row in dense:
        order = np.lexsort((terms, -row))
        out.append([str(terms[j]) for j in order[:top_n] if row[j] > 0])

    return out


def _anchor_source(
    cfg: dict[str, Any], anchor: str | None, structure: Structure | None
) -> str | None:
    """Which settings made the anchor: the anchor setting, focus, or both joined with +."""
    if not anchor:
        return None

    found = anchor_text(cfg["anchor"], structure) if structure is not None else None
    parts = [cfg["anchor"] if found else "",
             "focus" if focus_text(cfg["focus"]) else ""]  # fmt: skip

    return "+".join(p for p in parts if p)


def _mean_alignment(
    anchor_b: np.ndarray | None, members: np.ndarray, words: list[int]
) -> float | None:
    """Word-weighted mean probability that the walk from the chosen chunks ends at the anchor."""
    if anchor_b is None or not members.any():
        return None

    weights = np.asarray(words, dtype=float)[members]

    return _r(np.round(np.average(anchor_b[members, 0], weights=weights), 10))


def _share_above(anchor_b: np.ndarray | None, words: list[int], floor: float) -> float | None:
    """Word share of chunks whose anchor alignment is at least floor."""
    if anchor_b is None or not words:
        return None

    above = sum(w for w, b in zip(words, np.round(anchor_b[:, 0], 10), strict=True) if b >= floor)

    return _r(above / (sum(words) or 1))


def _r(value: float, places: int = 4) -> float:
    return round(float(value), places)


def _assemble(
    text: str, chunks: list[Chunk], words: list[int], labels: np.ndarray, smoothed: np.ndarray,
    Q: float, main: int, W: np.ndarray, knn: np.ndarray, info: dict[int, dict[str, Any]],
    anchor_b: np.ndarray | None, named_b: tuple[list[str], np.ndarray] | None,
    cfg: dict[str, Any], status: str, structure: Structure | None = None,
    anchor: str | None = None,
    chunk_terms: list[list[str]] | None = None, vec: Any = None, X: Any = None,
    hits: list[Counter[str]] | None = None,
) -> Result:  # fmt: skip
    share = shares(labels, words) if chunks else {}
    runs = segment(smoothed, main) if status == "ok" else []
    kind_of = {i: r["kind"] for r in runs for i in range(r["start"], r["end"] + 1)}
    names = named_b[0] if named_b else []
    best = named_b[1].argmax(axis=1) if named_b else None
    index = np.arange(len(chunks))
    report: dict[str, Any] = {
        "status": status,
        "min_count": cfg["chunk"]["min_count"],
        "n_chunks": len(chunks),
        "n_topics": len(info),
        "modularity": _r(Q),
        "main_topic": int(main),
        "anchor": anchor,
        "anchor_source": _anchor_source(cfg, anchor, structure),
        "topics": [
            {"id": t, "share": _r(share.get(t, 0.0)), **info[t],
             "central_line": _where(text, structure, chunks[info[t]["central_chunk"]].start,
                                    chunks[info[t]["central_chunk"]].start)["line"],
             "anchor_alignment": _mean_alignment(anchor_b, labels == t, words)}
            for t in sorted(info)
        ],  # fmt: skip
        "unassigned_share": _r(share.get(-1, 0.0)),
        "on_topic_share": _r(share.get(main, 0.0)) if status == "ok" else None,
        "anchor_score": _mean_alignment(anchor_b, index >= 0, words),
        "anchor_share_above": _share_above(anchor_b, words, cfg["align"]["on_topic_min"]),
        "segments": [
            {**r, **_where(text, structure, chunks[r["start"]].start, chunks[r["end"]].end),
             "chunks": r["end"] - r["start"] + 1,
             "words": sum(words[r["start"] : r["end"] + 1]),
             "anchor_alignment": _mean_alignment(
                 anchor_b, (index >= r["start"]) & (index <= r["end"]), words)}
            for r in runs
        ],  # fmt: skip
        "shifts": [r["start"] for r in runs[1:]],
        "labels": labels.tolist(),
    }

    if named_b:
        report["aligned"] = {
            k: _r(v) for k, v in aligned_shares(names, named_b[1], words).items()
        }

    report["chunks"] = [
        {
            "index": c.index, "start": c.start, "end": c.end,
            **_where(text, structure, c.start, c.end),
            "words": c.words, "raw_topic": int(labels[i]), "topic": int(smoothed[i]),
            "kind": kind_of.get(i),
            "anchor_alignment": None if anchor_b is None else _r(anchor_b[i, 0]),
            "aligned_to": names[int(best[i])] if best is not None else None,
            "named": {nm: _r(named_b[1][i, j]) for j, nm in enumerate(names)} if named_b else {},
            "terms": chunk_terms[i] if chunk_terms else [],
        }
        for i, c in enumerate(chunks)
    ]  # fmt: skip
    if hits is not None:
        _add_focus(report, hits, focus_terms(cfg["focus"]))

    report["sections"] = _sections(text, structure, report, vec, X, W, cfg)
    graph = _graph(report, W, knn, cfg)
    report["graph"] = _graph_summary(graph)

    return Result(report, graph, chunks)


def _sections(
    text: str, structure: Structure | None, report: dict[str, Any], vec: Any, X: Any,
    W: np.ndarray, cfg: dict[str, Any],
) -> list[dict[str, Any]]:  # fmt: skip
    """One record per titled part, with its title as an anchor for its own chunks."""
    found = headings(structure) if structure is not None else []
    chunks = report["chunks"]

    if not found or not chunks:
        return []

    bounds = [*[o for _, o, _ in found], len(text) + 1]
    out = []
    a = cfg["align"]
    walks: dict[str, np.ndarray] = {}

    def toward(anchor: str, members: list[dict[str, Any]]) -> float | None:
        """Mean probability the walk from these chunks ends at the anchor text."""
        if not members or vec is None or not anchor.strip():
            return None

        if anchor not in walks:
            walks[anchor] = align(vec, X, W, {"to": anchor}, a["sink"], a["boost"])[1][:, 0]

        return _r(np.mean([walks[anchor][c["index"]] for c in members]))

    for h, (level, offset, title) in enumerate(found):
        members = [c for c in chunks if offset <= c["start"] < bounds[h + 1]]
        total = sum(c["words"] for c in members)
        alignment = None

        if members and vec is not None and title.strip():
            _, B = align(vec, X, W, {"heading": title}, a["sink"], a["boost"])
            alignment = _r(np.mean([B[c["index"], 0] for c in members]))

        named = {}

        for nm in cfg["named"]:
            hit = sum(c["words"] for c in members if c["aligned_to"] == nm)
            named[nm] = _r(hit / total) if total else 0.0

        mean_anchor = None
        aligned = [c for c in members if c["anchor_alignment"] is not None]

        if aligned:
            mean_anchor = _r(sum(c["anchor_alignment"] * c["words"] for c in aligned)
                             / sum(c["words"] for c in aligned))  # fmt: skip

        evidence = _evidence(members, report["focus"]["keywords"]) if "focus" in report else {}
        part = structure.parts[structure.part_at(offset)] if structure is not None else None
        kin = _kin(structure, part) if structure is not None and part is not None else {}
        out.append({
            **evidence,
            "section": part.path if part is not None else "",
            "parent_alignment": toward(kin.get("parent", ""), members),
            "sibling_alignment": toward(kin.get("siblings", ""), members),
            "sibling_similarity": _sibling_similarity(structure, part, members, chunks, X),
            "heading": title, "level": level, "field": "title",
            "line": _where(text, structure, offset, offset)["line"],
            "heading_words": _content_words(title),
            "anchor_alignment": mean_anchor,
            "start": offset, "end": max((c["end"] for c in members), default=offset),
            "chunks": len(members), "words": total,
            "heading_alignment": alignment,
            "main_topic_share": _r(sum(c["words"] for c in members
                                       if c["topic"] == report["main_topic"]) / total)
            if total and report["status"] == "ok" else None,
            "n_topics": len({c["topic"] for c in members if c["topic"] >= 0}),
            "named": named,
        })  # fmt: skip

    return _parent_gaps(out, structure)


def _content_words(heading: str) -> int:
    """Words in a heading that are not on the English stop list."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    return sum(w not in ENGLISH_STOP_WORDS for w in re.findall(r"[a-z0-9']+", heading.lower()))


def _sibling_similarity(
    structure: Structure | None, part: Any, members: list[dict[str, Any]],
    chunks: list[dict[str, Any]], X: Any,
) -> float | None:  # fmt: skip
    """Mean TF-IDF cosine between this section's chunks and the chunks of the sections beside it
    (each sibling with everything under it)."""
    if structure is None or part is None or part.parent is None or X is None or not members:
        return None

    near = {i for c in structure.parts[part.parent].children if c != part.index
            for i in structure.descendants(c)}  # fmt: skip
    others = [c["index"] for c in chunks if structure.part_at(c["start"]) in near]

    if not others:
        return None

    sims = (X[[c["index"] for c in members]] @ X[others].T).toarray()

    return _r(float(np.mean(np.round(sims, 10))))


def _own_text(structure: Structure, index: int) -> str:
    """A section's own title, subtitle, text and items, without its child sections."""
    return " ".join(structure.text[b.start : b.end] for b in structure.parts[index].blocks)


def _kin(structure: Structure, part: Any) -> dict[str, str]:
    """The texts a section is compared with: its parent's own fields, and its siblings'."""
    if part.parent is None:
        return {}

    siblings = [c for c in structure.parts[part.parent].children if c != part.index]

    return {"parent": _own_text(structure, part.parent),
            "siblings": " ".join(_own_text(structure, c) for c in siblings)}  # fmt: skip


def _parent_gaps(rows: list[dict[str, Any]], structure: Structure | None) -> list[dict[str, Any]]:
    """parent_gap: a section's parent alignment minus the median of its siblings'. Negative means
    the section sits further from the shared parent than the sections beside it."""
    if structure is None:
        return rows

    by_path = {r["section"]: r for r in rows}

    for r in rows:
        part = next(p for p in structure.parts if p.path == r["section"])
        peers = [] if part.parent is None else [
            by_path[structure.parts[c].path]["parent_alignment"]
            for c in structure.parts[part.parent].children
            if c != part.index and structure.parts[c].path in by_path
            and by_path[structure.parts[c].path]["parent_alignment"] is not None
        ]  # fmt: skip
        own = r["parent_alignment"]
        r["parent_gap"] = _r(own - float(np.median(peers))) if peers and own is not None else None
        sims = [] if part.parent is None else [
            by_path[structure.parts[c].path]["sibling_similarity"]
            for c in structure.parts[part.parent].children
            if c != part.index and structure.parts[c].path in by_path
            and by_path[structure.parts[c].path]["sibling_similarity"] is not None
        ]  # fmt: skip
        mine = r["sibling_similarity"]
        gap = mine - float(np.median(sims)) if sims and mine is not None else None
        r["similarity_gap"] = _r(gap) if gap is not None else None

    return rows


# ---------- focus keywords ----------
_NON_WORD = re.compile(r"\W+")


def keyword_counts(
    text: str, chunks: list[Chunk], keywords: list[str], doc: Any = None
) -> list[Counter[str]]:
    """Occurrences of each keyword per chunk.

    With a spaCy doc over text, a keyword matches on lowercased surface form or on lemma, so
    "grinding" matches "grind"; a phrase matches as a phrase. Without one, on lowercased words.
    """
    starts: list[tuple[int, str]] = []

    if doc is not None:
        from spacy.matcher import PhraseMatcher

        from clarity.nlp import get_nlp

        nlp = get_nlp()
        found: set[tuple[int, str]] = set()

        for attr in ("LOWER", "LEMMA"):
            matcher = PhraseMatcher(nlp.vocab, attr=attr)

            for kw in keywords:
                matcher.add(kw, [nlp(kw.lower()) if attr == "LEMMA" else nlp.make_doc(kw)])

            for match_id, start, _ in matcher(doc):
                found.add((doc[start].idx, nlp.vocab.strings[match_id]))

        starts = sorted(found)
    else:
        lower = text.lower()

        for kw in keywords:
            parts = [re.escape(w) for w in _NON_WORD.split(kw.lower()) if w]
            pattern = re.compile(r"\b" + r"\W+".join(parts) + r"\b")
            starts += [(m.start(), kw) for m in pattern.finditer(lower)] if parts else []

    out: list[Counter[str]] = [Counter() for _ in chunks]

    for offset, kw in starts:
        for i, c in enumerate(chunks):
            if c.start <= offset < c.end:
                out[i][kw] += 1

    return out


def _evidence(members: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any]:
    """keyword_hits, keyword_coverage, keyword_chunk_share and missing_keywords over chunks."""
    present = {k for c in members for k in c["keywords_present"]}
    total = sum(c["words"] for c in members)
    with_hit = sum(c["words"] for c in members if c["keyword_hits"])

    return {
        "keyword_hits": sum(c["keyword_hits"] for c in members),
        "keyword_coverage": _r(len(present) / len(keywords)) if keywords else None,
        "keyword_chunk_share": _r(with_hit / total) if total else None,
        "missing_keywords": [k for k in keywords if k not in present],
    }


def _add_focus(report: dict[str, Any], hits: list[Counter[str]], keywords: list[str]) -> None:
    for chunk, found in zip(report["chunks"], hits, strict=True):
        chunk["keyword_hits"] = sum(found.values())
        chunk["keywords_present"] = [k for k in keywords if found[k]]

    report["focus"] = {"keywords": keywords, **_evidence(report["chunks"], keywords)}


# ---------- the graph as data ----------
def _graph(report: dict[str, Any], W: np.ndarray, knn: np.ndarray, cfg: dict[str, Any]) -> nx.Graph:
    """The chunk graph with node and edge attributes. Node ids are chunk indexes."""
    places = cfg["graph"]["measure_decimals"]
    G = nx.Graph()

    for c in report["chunks"]:
        G.add_node(
            c["index"], words=c["words"], line=c["line"], end_line=c["end_line"],
            topic=c["topic"], raw_topic=c["raw_topic"], kind=c["kind"],
            anchor_alignment=c["anchor_alignment"], aligned_to=c["aligned_to"],
            **{f"named.{k}": v for k, v in c["named"].items()},
        )  # fmt: skip

    n = W.shape[0]

    for i in range(n):
        for j in range(i + 1, n):
            if W[i, j] <= 0:
                continue

            adjacent = j == i + 1
            sim = float(knn[i, j])
            kind = "both" if adjacent and sim > 0 else "adjacent" if adjacent else "knn"
            weight = round(float(W[i, j]), places)
            G.add_edge(
                i, j, weight=weight, similarity=round(sim, places),
                adjacency=round(float(W[i, j]) - sim, places), kind=kind,
                distance=round(1.0 / weight, places),
            )  # fmt: skip

    _measure(G, cfg)

    return G


def _measure(G: nx.Graph, cfg: dict[str, Any]) -> None:
    places = cfg["graph"]["measure_decimals"]
    central = {}

    for node, data in G.nodes(data=True):
        within = between = 0.0

        for other in G[node]:
            w = G[node][other]["weight"]

            if data["raw_topic"] >= 0 and G.nodes[other]["raw_topic"] == data["raw_topic"]:
                within += w
            else:
                between += w

        data.update(
            degree=G.degree(node), weighted_degree=round(within + between, places),
            within_topic_weight=round(within, places), between_topic_weight=round(between, places),
        )  # fmt: skip

    if cfg["graph"]["centrality"] and G.number_of_nodes():
        betweenness = nx.betweenness_centrality(G, weight="distance", normalized=True)
        closeness = nx.closeness_centrality(G, distance="distance")
        central = {n: (betweenness[n], closeness[n]) for n in G.nodes}

    for node, data in G.nodes(data=True):
        b, c = central.get(node, (None, None))
        data["betweenness"] = None if b is None else round(b, places)
        data["closeness"] = None if c is None else round(c, places)


def _graph_summary(G: nx.Graph) -> dict[str, Any]:
    return {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}


def mark_central(result: Result) -> None:
    centrals = {t["central_chunk"] for t in result.report["topics"]}

    for node, data in result.graph.nodes(data=True):
        data["is_central"] = node in centrals


def node_records(result: Result) -> list[dict[str, Any]]:
    out = []

    for node in sorted(result.graph.nodes):
        d = result.graph.nodes[node]
        c = result.chunks[node]
        out.append({
            "index": node, "topic": d["topic"], "raw_topic": d["raw_topic"], "kind": d["kind"],
            "words": d["words"], "degree": d["degree"], "weighted_degree": d["weighted_degree"],
            "within_topic_weight": d["within_topic_weight"],
            "between_topic_weight": d["between_topic_weight"],
            "betweenness": d["betweenness"], "closeness": d["closeness"],
            "is_central": d.get("is_central", False), "line": d["line"],
            "start": c.start, "end": c.end,
        })  # fmt: skip

    return out


def edge_records(result: Result) -> list[dict[str, Any]]:
    G, out = result.graph, []

    for i, j in sorted((min(e), max(e)) for e in G.edges):
        d = G[i][j]
        out.append({
            "source": i, "target": j, "weight": d["weight"], "similarity": d["similarity"],
            "adjacent": d["kind"] in ("adjacent", "both"), "kind": d["kind"],
            "same_topic": G.nodes[i]["raw_topic"] >= 0
            and G.nodes[i]["raw_topic"] == G.nodes[j]["raw_topic"],
            "start": result.chunks[i].start, "end": result.chunks[j].end,
        })  # fmt: skip

    return out


def run(
    text: str, settings: dict[str, Any] | None = None, **kwargs: Any
) -> Result:
    """analyze() with central chunks marked on the graph."""
    result = analyze(text, settings, **kwargs)
    mark_central(result)
    structure = kwargs.get("structure")
    result.report["child_sections"] = len(structure.parts) - 1 if structure is not None else 0

    return result


def lemma_docs(text: str, doc: Any, chunks: list[Chunk]) -> list[str]:
    """One lemma string per chunk from a spaCy doc over text."""
    out = []

    for c in chunks:
        span = doc.char_span(c.start, c.end, alignment_mode="expand")
        out.append(" ".join(t.lemma_.lower() for t in span if not t.is_space) if span else c.text)

    return out


def for_analysis(analysis: Any, settings: dict[str, Any] | None = None) -> Result:
    """The topic result for a clarity Analysis, computed once per effective settings."""
    cfg = effective(settings) if settings is not None else effective()
    key = settings_key(cfg)
    cache = analysis._cache

    if key not in cache:
        sents = [(s.start_char, s.end_char) for s in analysis.sentences]
        lemmas = None

        if cfg["vectorize"]["use_lemmas"]:
            ch = cfg["chunk"]
            chunks = chunk_text(analysis.text, ch["min_words"], ch["unit"], ch["max_words"],
                                analysis.structure, sents)  # fmt: skip
            lemmas = lemma_docs(analysis.text, analysis.doc, chunks)

        cache[key] = run(analysis.text, cfg, structure=analysis.structure, sentences=sents,
                         lemmas=lemmas,
                         doc=analysis.doc)  # fmt: skip

    result: Result = cache[key]

    return result


# ---------- output ----------
def graph_json(result: Result) -> dict[str, Any]:
    """Node-link data with stable ordering."""
    data = nx.node_link_data(result.graph, edges="edges")
    data["nodes"] = sorted(data["nodes"], key=lambda n: n["id"])
    data["edges"] = sorted(data["edges"], key=lambda e: (e["source"], e["target"]))

    return dict(data)


def graph_graphml(result: Result) -> str:
    H = _plain_graph(result)

    return "\n".join(nx.generate_graphml(H))


def _plain_graph(result: Result) -> nx.Graph:
    """A copy with sorted nodes and edges and no None values (GraphML has no null)."""
    G, H = result.graph, nx.Graph()

    for n in sorted(G.nodes):
        H.add_node(n, **{k: v for k, v in sorted(G.nodes[n].items()) if v is not None})

    for i, j in sorted((min(e), max(e)) for e in G.edges):
        H.add_edge(i, j, **dict(sorted(G[i][j].items())))

    return H


def graph_dot(result: Result) -> str:
    H = _plain_graph(result)
    lines = ["graph topics {"]

    def attrs(d: dict[str, Any]) -> str:
        return ", ".join(f'"{k}"={json.dumps(v)}' for k, v in d.items())

    for n, d in H.nodes(data=True):
        lines.append(f"  {n} [{attrs(d)}];")

    for i, j, d in H.edges(data=True):
        lines.append(f"  {i} -- {j} [{attrs(d)}];")

    lines.append("}")

    return "\n".join(lines)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_text(result: Result, source: str) -> str:
    """The report for a terminal. Positions are line numbers, never chunk indexes."""
    r = result.report
    chunks = r["chunks"]
    out = [f"{source} · {r['n_chunks']} chunks · {r['n_topics']} topics · "
           f"modularity {r['modularity']:g}"]  # fmt: skip

    if r["status"] != "ok":
        out.append(f"{r['status']}: {STATUS_DOCS[r['status']]} "
                   f"(min_count {r['min_count']}); no topics reported")  # fmt: skip

    anchor = f'anchor: "{r["anchor"]}"' if r["anchor"] else "anchor: none (main is the largest)"
    out += [f"{anchor} · main topic {r['main_topic']}", "", "TOPICS"]

    for t in r["topics"]:
        terms = ", ".join(t["terms"]) or "(no terms)"
        out.append(f"  {t['id']:>2}  {_pct(t['share']):>6}  {terms:<56} central: line "
                   f"{t['central_line']}")  # fmt: skip

    on_topic = "n/a" if r["on_topic_share"] is None else _pct(r["on_topic_share"])
    out.append(f"  unassigned {_pct(r['unassigned_share'])} · on-topic {on_topic}")
    out += ["", "SEGMENTS"]

    for s in r["segments"]:
        lines = f"lines {s['line']}-{s['end_line']}"
        field = f" · {s['section']} {s['field']}".rstrip() if s.get("section") else ""
        out.append(f"  {lines:<16}topic {s['topic']:>2}  {s['kind']:<11}{s['words']} words{field}")

    shifts = [str(chunks[i]["line"]) for i in r["shifts"]]
    out.append("  shifts at lines " + (", ".join(shifts) if shifts else "none"))

    if "aligned" in r:
        out += ["", "NAMED TOPICS"]
        out += [f"  {name:<16}{_pct(share):>6}" for name, share in r["aligned"].items()]

    if "focus" in r:
        f = r["focus"]
        out += ["", "FOCUS KEYWORDS", f"  coverage {_pct(f['keyword_coverage'])} · "
                f"{f['keyword_hits']} hits · in {_pct(f['keyword_chunk_share'] or 0)} of the words",
                "  missing: " + (", ".join(f["missing_keywords"]) or "none")]  # fmt: skip

    if r["sections"]:
        out += ["", "SECTIONS"]

        for s in r["sections"]:
            fit = "n/a" if s["heading_alignment"] is None else f"{s['heading_alignment']:.3f}"
            main = "n/a" if s["main_topic_share"] is None else _pct(s["main_topic_share"])
            out.append(f"  line {s['line']:<5}{s['heading'][:40]:<42}heading fit {fit:<7}"
                       f"main {main}")  # fmt: skip

    g = r["graph"]
    out += ["", f"GRAPH  {g['nodes']} nodes · {g['edges']} edges  (--graph json|graphml|dot)"]

    return "\n".join(out)


def export(result: Result, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(graph_json(result), indent=2, sort_keys=True)

    if fmt == "graphml":
        return graph_graphml(result)

    if fmt == "dot":
        return graph_dot(result)

    raise ValueError(f"unknown graph format {fmt!r}; choose json, graphml or dot")
