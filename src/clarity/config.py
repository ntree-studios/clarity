"""Rule and category configuration: bundled default pack plus user overrides."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

COUNT_SCOPES = ("document", "section", "paragraph", "sentence", "clause")
POSITIONS = (
    "anywhere",
    "sentence-initial",
    "clause-initial",
    "sentence-final",
    "paragraph-final",
    "section-final",
)
CONFIDENCES = ("exact", "inferred")
SEVERITIES = ("info", "warning", "error")
BACKENDS = ("phrase", "dependency", "structural", "composite")


class ConfigError(ValueError):
    """Raised for malformed configuration."""


@dataclass
class Rule:
    id: str
    category: int | str
    backend: str = "phrase"
    severity: str = "warning"
    confidence: str = "exact"
    max_per_1k: float | None = None
    max_per_scope: int | None = None
    count_scope: str = "document"
    position: str = "anywhere"
    message: str = ""
    suggestion: str | None = None
    # phrase backend
    phrases: list[str] = field(default_factory=list)
    lower_phrases: list[str] = field(default_factory=list)
    pattern: list[Any] | None = None
    match: str = "lemma"
    # dependency backend
    patterns: list[list[dict[str, Any]]] = field(default_factory=list)
    anchor: str | None = None
    concreteness_max: float | None = None
    suppress_if: list[Any] = field(default_factory=list)
    active_when: Any = None
    allowance_when: list[Any] = field(default_factory=list)
    # composite backend: findings of other rules that must (or must not) share a scope
    requires_all: list[Any] = field(default_factory=list)
    requires_any: list[Any] = field(default_factory=list)
    requires_none: list[Any] = field(default_factory=list)
    note: str = ""
    next_lemma: list[str] = field(default_factory=list)
    experimental: bool = False
    fixtures_exempt: bool = False
    # structural backend
    function: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Category:
    n: int
    id: str
    name: str
    weight: float = 1.0
    cap: float = 20.0


@dataclass
class Config:
    categories: dict[int, Category]
    rules: list[Rule]
    severity_weights: dict[str, float]
    readability: dict[str, Any] = field(default_factory=dict)
    prose_metrics: dict[str, Any] = field(default_factory=dict)


def _read_default() -> dict[str, Any]:
    text = resources.files("clarity").joinpath("default.yml").read_text(encoding="utf-8")

    return _parse(text)


def _parse(text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML: {exc}") from exc

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")

    return data


def _build_rule(raw: dict[str, Any]) -> Rule:
    if "id" not in raw:
        raise ConfigError(f"rule missing id: {raw}")

    rid = raw["id"]
    known = set(Rule.__dataclass_fields__)
    unknown = set(raw) - known - {"disabled"}

    if {"scope", "clause_initial"} & unknown:
        raise ConfigError(
            f"rule {rid}: 'scope' and 'clause_initial' were replaced by count_scope "
            "(document, section, paragraph, sentence, clause) and position "
            "(anywhere, sentence-initial, clause-initial, sentence-final, paragraph-final, "
            "section-final)"
        )

    if unknown:
        raise ConfigError(f"rule {rid}: unknown keys {sorted(unknown)}")

    kwargs = {k: v for k, v in raw.items() if k in known}
    rule = Rule(**kwargs)

    for name, value, allowed in (
        ("count_scope", rule.count_scope, COUNT_SCOPES),
        ("position", rule.position, POSITIONS),
        ("confidence", rule.confidence, CONFIDENCES),
        ("severity", rule.severity, SEVERITIES),
        ("backend", rule.backend, BACKENDS),
    ):
        if value not in allowed:
            raise ConfigError(f"rule {rid}: {name} must be one of {allowed}, got {value!r}")

    _resolve_allowance(rule)

    return rule


def _resolve_allowance(rule: Rule) -> None:
    """max_per_1k belongs to document scope, max_per_scope to every other scope."""
    if rule.count_scope == "document":
        if rule.max_per_scope is not None:
            raise ConfigError(
                f"rule {rule.id}: max_per_scope is not valid at count_scope document; "
                "use max_per_1k"
            )

        rule.max_per_1k = 0 if rule.max_per_1k is None else rule.max_per_1k
    else:
        if rule.max_per_1k is not None:
            raise ConfigError(
                f"rule {rule.id}: max_per_1k is not valid at count_scope {rule.count_scope}; "
                "use max_per_scope"
            )

        rule.max_per_scope = 0 if rule.max_per_scope is None else rule.max_per_scope

    allowance = rule.max_per_1k if rule.count_scope == "document" else rule.max_per_scope

    if allowance is not None and allowance < 0:
        raise ConfigError(f"rule {rule.id}: allowance must be >= 0")


def _watchlist_rule(entry: dict[str, Any]) -> dict[str, Any]:
    """Expand a watchlist entry into a rule dict under the watchlist category."""
    term = entry.get("term")

    if not term or not isinstance(term, str):
        raise ConfigError(f"watchlist entry needs a term: {entry}")

    governed = bool(entry.get("require_concrete_governor", False))
    rule: dict[str, Any] = {
        "id": term,
        "category": "watchlist",
        "phrases": [term],
        "match": "lower" if entry.get("match") == "phrase" else "lemma",
        "max_per_1k": entry.get("max_per_1k", 0),
        "severity": entry.get("severity", "warning"),
        "confidence": "inferred" if governed else "exact",
        "message": f'Watchlist term "{term}".',
        "fixtures_exempt": True,
    }

    if governed:
        rule["concreteness_max"] = 3.0

    return rule


@dataclass
class Layer:
    """One config file's data and where it came from."""

    source: str
    data: dict[str, Any]


# scope ("rule:id", "category:id", "readability", ...) -> field -> [(source, shown, note)]
Provenance = dict[str, dict[str, list[tuple[str, str, str]]]]
TOP_LEVEL = {
    "version", "severity_weights", "categories", "rules", "watchlist", "readability",
    "prose_metrics", "profile",
}  # fmt: skip


def _shown(value: Any) -> str:
    return f"{len(value)} items" if isinstance(value, list) else str(value)


def record(
    prov: Provenance, scope: str, field_: str, source: str, shown: Any, note: str = ""
) -> None:
    prov.setdefault(scope, {}).setdefault(field_, []).append((source, _shown(shown), note))


def merge_fields(
    target: dict[str, Any], new: dict[str, Any], source: str, prov: Provenance, scope: str
) -> None:
    """Per-key merge: scalars replace, lists replace, name+ appends, name- removes."""
    for key, value in new.items():
        if key == "id":
            continue

        if key == "enabled":
            target["disabled"] = not bool(value)
            record(prov, scope, "enabled", source, bool(value))

            continue

        if key.endswith(("+", "-")):
            _edit_list(target, key, value, source, prov, scope)

            continue

        target[key] = value
        record(prov, scope, key, source, value)


def _edit_list(
    target: dict[str, Any], key: str, value: Any, source: str, prov: Provenance, scope: str
) -> None:
    name, op = key[:-1], key[-1]
    inherited = target.get(name)

    if not isinstance(value, list):
        raise ConfigError(f"{source}: {scope}: '{key}' must be a list")

    if op == "+":
        base = inherited if isinstance(inherited, list) else []
        target[name] = [*base, *[v for v in value if v not in base]]
        record(prov, scope, name, source, f"+ {len(value)} items", "append")

        return

    if not isinstance(inherited, list):
        raise ConfigError(f"{source}: {scope}: '{key}' has no inherited {name} list to remove from")

    missing = [v for v in value if v not in inherited]

    if missing:
        raise ConfigError(
            f"{source}: {scope}: '{key}' removes {missing}, which are not in the inherited {name}"
        )

    target[name] = [v for v in inherited if v not in value]
    record(prov, scope, name, source, f"- {len(value)} items", "remove")


def _layer_categories(merged: dict[str, Any], layer: Layer, prov: Provenance) -> None:
    raw = layer.data.get("categories") or []
    by_id = {c.get("id"): n for n, c in merged["categories"].items()}
    items = (
        [{"id": k, **v} for k, v in raw.items()] if isinstance(raw, dict) else list(raw)
    )

    for cat in items:
        n = cat.get("n", by_id.get(cat.get("id")))

        if n is None:
            name = cat.get("id")
            raise ConfigError(f"{layer.source}: category {name!r} needs an n or must exist")

        target = merged["categories"].setdefault(n, {"n": n})

        if "id" in cat:
            target["id"] = cat["id"]

        merge_fields(target, {**cat, "n": n}, layer.source, prov, f"category:{cat.get('id', n)}")
        by_id[target.get("id")] = n


def merge_layers(layers: list[Layer]) -> tuple[dict[str, Any], Provenance]:
    """Merge layers in order; later layers are nearer and win."""
    merged: dict[str, Any] = {
        "severity_weights": {}, "categories": {}, "rules": {}, "readability": {},
        "prose_metrics": {}, "profile": None, "profile_source": None,
    }  # fmt: skip
    prov: Provenance = {}

    for layer in layers:
        data = layer.data
        unknown = set(data) - TOP_LEVEL

        if unknown:
            raise ConfigError(f"{layer.source}: unknown top-level keys {sorted(unknown)}")

        for block in ("severity_weights", "readability", "prose_metrics"):
            merge_fields(merged[block], data.get(block) or {}, layer.source, prov, block)

        _layer_categories(merged, layer, prov)

        if "profile" in data:
            merged["profile"], merged["profile_source"] = data["profile"], layer.source

        entries = [_watchlist_rule(e) for e in data.get("watchlist") or []]

        for rule in [*entries, *(data.get("rules") or [])]:
            if "id" not in rule:
                raise ConfigError(f"{layer.source}: rule missing id: {rule}")

            target = merged["rules"].setdefault(rule["id"], {"id": rule["id"]})
            merge_fields(target, rule, layer.source, prov, f"rule:{rule['id']}")

    return merged, prov


def _last_source(prov: Provenance, scope: str) -> str:
    sources = [e[0] for events in prov.get(scope, {}).values() for e in events]

    return sources[-1] if sources else "config"


def build_config(merged: dict[str, Any], prov: Provenance) -> Config:
    """Validate the merged data and build the typed Config."""
    categories: dict[int, Category] = {}

    for n, raw in merged["categories"].items():
        missing = [k for k in ("id", "weight", "cap") if k not in raw]

        if missing:
            src = _last_source(prov, f"category:{raw.get('id', n)}")
            raise ConfigError(f"{src}: category {raw.get('id', n)!r} is missing {missing}")

        fields_ = Category.__dataclass_fields__
        categories[n] = Category(**{k: v for k, v in raw.items() if k in fields_})

    by_slug = {c.id: n for n, c in categories.items()}
    rules: list[Rule] = []

    for rid, raw in merged["rules"].items():
        if raw.get("disabled"):
            continue

        try:
            rule = _build_rule(raw)
            _resolve_category(rule, categories, by_slug)
        except ConfigError as exc:
            raise ConfigError(f"{_last_source(prov, f'rule:{rid}')}: {exc}") from exc

        rules.append(rule)

    from clarity import composition

    try:
        composition.validate(rules, categories)
    except composition.CompositionError as exc:
        raise ConfigError(f"{_last_source(prov, f'rule:{exc.rule_id}')}: {exc}") from exc

    return Config(
        categories,
        rules,
        merged["severity_weights"],
        merged["readability"],
        merged["prose_metrics"],
    )


def _resolve_category(rule: Rule, categories: dict[int, Category], by_slug: dict[str, int]) -> None:
    if isinstance(rule.category, str):
        if rule.category not in by_slug:
            raise ConfigError(f"rule {rule.id}: unknown category {rule.category}")

        rule.category = by_slug[rule.category]

    if rule.category not in categories:
        raise ConfigError(f"rule {rule.id}: unknown category {rule.category}")


def load_config(path: str | Path | None = None, text: str | None = None) -> Config:
    """Load the bundled pack, then apply overrides from a file or YAML text."""
    layers = [Layer("bundled", _read_default())]

    if text is not None:
        layers.append(Layer("<text>", _parse(text)))
    elif path is not None:
        try:
            layers.append(Layer(str(path), _parse(Path(path).read_text(encoding="utf-8"))))
        except OSError as exc:
            raise ConfigError(f"cannot read config {path}: {exc}") from exc

    merged, prov = merge_layers(layers)

    return build_config(merged, prov)


def describe_rules(config: Config, category: int | None = None) -> list[dict[str, Any]]:
    """Flat rule descriptions for listing, optionally limited to one category number."""
    rows = []

    for rule in config.rules:
        if category is not None and rule.category != category:
            continue

        cat = config.categories[int(rule.category)]
        rows.append(
            {
                "id": rule.id,
                "category": cat.id,
                "category_number": cat.n,
                "backend": rule.backend,
                "severity": rule.severity,
                "confidence": rule.confidence,
                "count_scope": rule.count_scope,
                "position": rule.position,
                "max_per_1k": rule.max_per_1k,
                "max_per_scope": rule.max_per_scope,
                "message": rule.message,
            }
        )

    return rows
