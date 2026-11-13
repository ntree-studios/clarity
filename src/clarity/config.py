"""Rule and category configuration: bundled default pack plus user overrides."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

SCOPES = ("document", "section", "paragraph", "sentence")
CONFIDENCES = ("exact", "inferred")
SEVERITIES = ("info", "warning", "error")
BACKENDS = ("phrase", "dependency", "structural")


class ConfigError(ValueError):
    """Raised for malformed configuration."""


@dataclass
class Rule:
    id: str
    category: int | str
    backend: str = "phrase"
    severity: str = "warning"
    confidence: str = "exact"
    max_per_1k: float = 0
    scope: str = "sentence"
    message: str = ""
    suggestion: str | None = None
    # phrase backend
    phrases: list[str] = field(default_factory=list)
    pattern: list[Any] | None = None
    match: str = "lemma"
    clause_initial: bool = False
    # dependency backend
    patterns: list[list[dict[str, Any]]] = field(default_factory=list)
    anchor: str | None = None
    concreteness_max: float | None = None
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

    if unknown:
        raise ConfigError(f"rule {rid}: unknown keys {sorted(unknown)}")

    kwargs = {k: v for k, v in raw.items() if k in known}
    rule = Rule(**kwargs)

    for name, value, allowed in (
        ("scope", rule.scope, SCOPES),
        ("confidence", rule.confidence, CONFIDENCES),
        ("severity", rule.severity, SEVERITIES),
        ("backend", rule.backend, BACKENDS),
    ):
        if value not in allowed:
            raise ConfigError(f"rule {rid}: {name} must be one of {allowed}, got {value!r}")

    if rule.max_per_1k < 0:
        raise ConfigError(f"rule {rid}: max_per_1k must be >= 0")

    return rule


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
    }

    if governed:
        rule["concreteness_max"] = 3.0

    return rule


def _merge(base: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "severity_weights": dict(base.get("severity_weights", {})),
        "categories": {c["n"]: dict(c) for c in base.get("categories", [])},
        "rules": {r["id"]: dict(r) for r in base.get("rules", [])},
        "readability": dict(base.get("readability", {})),
    }
    merged["readability"].update(user.get("readability", {}) or {})
    merged["severity_weights"].update(user.get("severity_weights", {}) or {})

    for cat in user.get("categories", []) or []:
        merged["categories"].setdefault(cat["n"], {}).update(cat)

    for entry in user.get("watchlist", []) or []:
        rule = _watchlist_rule(entry)
        merged["rules"].setdefault(rule["id"], {}).update(rule)

    for rule in user.get("rules", []) or []:
        if "id" not in rule:
            raise ConfigError(f"rule missing id: {rule}")

        merged["rules"].setdefault(rule["id"], {}).update(rule)

    return merged


def load_config(path: str | Path | None = None, text: str | None = None) -> Config:
    """Load the bundled pack, then apply overrides from a file or YAML text."""
    user: dict[str, Any] = {}

    if text is not None:
        user = _parse(text)
    elif path is not None:
        try:
            user = _parse(Path(path).read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"cannot read config {path}: {exc}") from exc

    merged = _merge(_read_default(), user)
    categories = {n: Category(**c) for n, c in merged["categories"].items()}
    rules = [_build_rule(r) for r in merged["rules"].values() if not r.get("disabled")]

    by_slug = {c.id: n for n, c in categories.items()}

    for rule in rules:
        if isinstance(rule.category, str):
            if rule.category not in by_slug:
                raise ConfigError(f"rule {rule.id}: unknown category {rule.category}")

            rule.category = by_slug[rule.category]

        if rule.category not in categories:
            raise ConfigError(f"rule {rule.id}: unknown category {rule.category}")

    return Config(categories, rules, merged["severity_weights"], merged["readability"])


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
                "max_per_1k": rule.max_per_1k,
                "scope": rule.scope,
                "message": rule.message,
            }
        )

    return rows
