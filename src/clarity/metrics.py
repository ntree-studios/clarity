"""The metric registry and the analysis object metrics read.

A metric is a named measurement with declared scopes and a return shape. Registering one makes
it addressable everywhere: the prose metrics block, baselines and drift. The registry is the one
Python extension point for new measurements.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from spacy.tokens import Doc, Span

from clarity import markdown
from clarity.clauses import Clause, clauses
from clarity.matchers.common import sentences

SCOPES = ("token", "sentence", "clause", "paragraph", "section", "list_item", "heading", "document")


@dataclass(frozen=True)
class Metric:
    name: str
    scopes: tuple[str, ...]
    returns: str
    scalars: tuple[str, ...]
    fn: Callable[[Analysis], Any]
    doc: str = ""
    needs_markdown: bool = False


REGISTRY: dict[str, Metric] = {}


def metric(
    name: str,
    *,
    scopes: tuple[str, ...] = ("document",),
    returns: str = "mapping",
    scalars: tuple[str, ...] = (),
    needs_markdown: bool = False,
) -> Callable[[Callable[[Analysis], Any]], Callable[[Analysis], Any]]:
    """Register fn as a metric. scalars are the result keys (dotted for nesting) that baselines
    and drift track."""
    unknown = set(scopes) - set(SCOPES)

    if unknown:
        raise ValueError(f"metric {name}: unknown scopes {sorted(unknown)}")

    def wrap(fn: Callable[[Analysis], Any]) -> Callable[[Analysis], Any]:
        REGISTRY[name] = Metric(name, scopes, returns, scalars, fn, (fn.__doc__ or "").strip(),
                                needs_markdown)  # fmt: skip

        return fn

    return wrap


@dataclass
class Analysis:
    """One parse, shared. Metrics read from it and results are cached."""

    doc: Doc
    text: str
    raw: str = ""
    _cache: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.raw = self.raw or self.text

    @cached_property
    def sentences(self) -> list[Span]:
        return sentences(self.doc)

    @cached_property
    def clauses(self) -> list[Clause]:
        return clauses(self.doc)

    @cached_property
    def paragraphs(self) -> list[tuple[int, int]]:
        return markdown.prose_paragraphs(self.text)

    @cached_property
    def model(self) -> markdown.Model:
        return markdown.parse(self.raw)

    @cached_property
    def words(self) -> int:
        return sum(1 for t in self.doc if not t.is_punct and not t.is_space)

    def paragraph_sentences(self) -> list[list[Span]]:
        out = []

        for start, end in self.paragraphs:
            group = [s for s in self.sentences if start <= s.start_char < end]

            if group:
                out.append(group)

        return out

    def get(self, name: str) -> Any:
        if name not in REGISTRY:
            raise KeyError(f"unknown metric {name!r}")

        if name not in self._cache:
            self._cache[name] = REGISTRY[name].fn(self)

        return self._cache[name]


def load_registry() -> dict[str, Metric]:
    """The registry with every built-in metric registered. Import them on first use."""
    importlib.import_module("clarity.prose_metrics")

    return REGISTRY


def get_at(analysis: Analysis, name: str, span: Span) -> Any:
    """A metric measured over one span (a sentence or paragraph) instead of the document."""
    entry = REGISTRY[name]

    if entry.scopes == ("document",):
        raise ValueError(f"metric {name} only supports document scope")

    return Analysis(span.as_doc(), span.text).get(name)


def scalar(value: Any, key: str) -> float | None:
    """Follow a dotted key through a metric result. None when absent or not a number."""
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None

    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def extract(results: dict[str, Any]) -> dict[str, float]:
    """Tracked scalars from metric results: 'name' for a single key, 'name.key' otherwise."""
    out: dict[str, float] = {}

    for name, result in results.items():
        if name not in REGISTRY:
            continue

        entry = REGISTRY[name]

        for key in entry.scalars:
            value = scalar(result, key)

            if value is not None:
                out[name if len(entry.scalars) == 1 else f"{name}.{key}"] = value

    return out


def scalars(analysis: Analysis, names: list[str] | None = None) -> dict[str, float]:
    """Every tracked scalar of the chosen metrics, computed from the analysis."""
    return extract({name: analysis.get(name) for name in names or list(REGISTRY)})
