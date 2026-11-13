"""Everything a rule author can address, read from the code that enforces it.

`clarity surface` prints it, `clarity://surface` serves it to MCP clients, and the README sections
between `<!-- surface:NAME -->` markers are rendered from it. A table typed by hand drifts from the
schema; this one cannot.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from clarity import composition
from clarity.config import (
    BACKEND_FIELDS,
    BACKEND_REQUIRES,
    BACKENDS,
    CONFIDENCES,
    COUNT_SCOPES,
    POSITIONS,
    SEVERITIES,
    Config,
    Rule,
)
from clarity.metrics import load_registry

SECTIONS = ("fields", "enums", "conditions", "metrics", "functions", "categories", "mcp", "sets")
MATCHES = ("lemma", "lower")

# One line per Rule field. A test fails if a field is added without a line here.
FIELD_DOCS = {
    "id": "unique slug",
    "category": "a category id or number (see categories)",
    "backend": "how the rule matches",
    "severity": "weight of a finding",
    "confidence": "exact is a deterministic match; inferred rests on a heuristic",
    "max_per_1k": "allowed matches per 1,000 words; only at count_scope document",
    "max_per_scope": "allowed matches per unit; at every other count_scope",
    "count_scope": "the unit the allowance is counted in",
    "position": "where a match must sit to count",
    "message": "text shown with each finding",
    "suggestion": "replacement wording shown with the finding",
    "phrases": "words or phrases, matched on lemmas unless match is lower",
    "lower_phrases": "phrases matched on case-folded surface text",
    "pattern": "a spaCy Matcher token pattern",
    "match": "lemma or lower, for phrases",
    "patterns": "spaCy DependencyMatcher patterns",
    "anchor": "the pattern node a finding spans",
    "concreteness_max": "fire only when the governed noun rates below this (1 to 5)",
    "next_lemma": "the match must be followed by one of these lemmas",
    "experimental": "report findings but leave them out of the score; skips the fixture rule",
    "fixtures_exempt": "skip the fixture rule (generated rules only)",
    "function": "a registered structural function (see functions)",
    "params": "values the structural function reads",
    "suppress_if": "conditions that drop a match; it uses no allowance",
    "active_when": "metric conditions that must hold for the rule to apply",
    "allowance_when": "allowances that replace the default when a condition holds",
    "requires_all": "composite: every member must have a finding in the scope",
    "requires_any": "composite: at least one member must have a finding in the scope",
    "requires_none": "composite: no member may have a finding in the scope",
    "note": "composite: text added to the finding",
}

CONDITION_DOCS = {
    "metric": "{metric, op, value, key?} where op is one of "
    + ", ".join(composition.OPS)
    + ". key picks a scalar of the metric; the default is its first tracked scalar.",
    "near": "suppress_if: {pos | lemma | ent | pattern, within: N} tests tokens near the match.",
    "in_scope": "suppress_if: {count_scope, rule} holds when another rule matches in that scope.",
    "over_allowance": "allowance_when: {over_allowance: category, <allowance field>} tightens "
    "a rule when another category is over its allowance.",
    "requires": "composite members are {rule, min_count?}; one level, no composite members.",
}


def _default(field: Any) -> str:
    if field.default is not MISSING:
        return "none" if field.default is None else str(field.default)

    if field.default_factory is not MISSING:
        value = field.default_factory()

        return "empty" if not value else str(value)

    return "required"


def _group(name: str) -> str:
    return next((b for b, names in BACKEND_FIELDS.items() if name in names), "common")


def _required(name: str) -> str:
    if name in ("id", "category"):
        return "always"

    for backend, options in BACKEND_REQUIRES.items():
        for choice in options:
            if name in choice:
                return f"{backend}: " + ("one of these" if len(choice) > 1 else "yes")

    return ""


def rule_fields() -> list[dict[str, str]]:
    return [
        {"name": f.name, "applies_to": _group(f.name), "default": _default(f),
         "required": _required(f.name), "description": FIELD_DOCS.get(f.name, "")}
        for f in fields(Rule)
    ]  # fmt: skip


def enums() -> dict[str, list[str]]:
    return {
        "backend": list(BACKENDS), "count_scope": list(COUNT_SCOPES),
        "position": list(POSITIONS), "severity": list(SEVERITIES),
        "confidence": list(CONFIDENCES), "match": list(MATCHES),
        "op": list(composition.OPS),
    }  # fmt: skip


def metrics() -> list[dict[str, Any]]:
    return [
        {"name": m.name, "scopes": list(m.scopes), "returns": m.returns,
         "scalars": list(m.scalars), "description": m.doc.splitlines()[0] if m.doc else ""}
        for m in load_registry().values()
    ]  # fmt: skip


def _first_line(doc: str | None) -> str:
    return (doc or "").strip().splitlines()[0] if (doc or "").strip() else ""


def functions() -> list[dict[str, str]]:
    from clarity.matchers.structural import REGISTRY

    return [
        {"name": name, "description": _first_line(fn.__doc__)}
        for name, fn in sorted(REGISTRY.items())
    ]  # fmt: skip


def categories(config: Config) -> list[dict[str, Any]]:
    return [{"n": n, "id": c.id, "weight": c.weight, "cap": c.cap}
            for n, c in sorted(config.categories.items())]  # fmt: skip


def mcp() -> dict[str, list[str]]:
    from clarity.mcp_server import server

    async def listed() -> dict[str, list[str]]:
        return {
            "tools": [t.name for t in await server.list_tools()],
            "prompts": [p.name for p in await server.list_prompts()],
            "resources": sorted(
                [str(r.uri) for r in await server.list_resources()]
                + [str(t.uri_template) for t in await server.list_resource_templates()]
            ),
        }

    return asyncio.run(listed())


def build(config: Config) -> dict[str, Any]:
    return {
        "fields": rule_fields(),
        "enums": enums(),
        "conditions": CONDITION_DOCS,
        "metrics": metrics(),
        "functions": functions(),
        "categories": categories(config),
        "mcp": mcp(),
        "sets": {"names": [], "note": "Named sets are not part of this schema."},
        "required": {b: [list(o) for o in opts] for b, opts in BACKEND_REQUIRES.items()},
    }


# ---- rendering ----------------------------------------------------------------------------


def _table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]

    return "\n".join(lines)


def _code(items: list[str]) -> str:
    return ", ".join(f"`{i}`" for i in items)


def render(section: str, data: dict[str, Any]) -> str:
    """One section as markdown. The same text goes to the terminal, MCP and the README."""
    if section == "fields":
        rows = [[f"`{f['name']}`", f["applies_to"], f["default"], f["required"], f["description"]]
                for f in data["fields"]]  # fmt: skip

        return _table(["Field", "Backend", "Default", "Required", "Meaning"], rows)

    if section == "enums":
        return "\n".join(f"- `{k}`: {_code(v)}" for k, v in data["enums"].items())

    if section == "conditions":
        return "\n".join(f"- `{k}`: {v}" for k, v in data["conditions"].items())

    if section == "metrics":
        rows = [[f"`{m['name']}`", _code(m["scopes"]), _code(m["scalars"]) or "none"]
                for m in data["metrics"]]  # fmt: skip

        return _table(["Metric", "Scopes", "Tracked scalars"], rows)

    if section == "functions":
        return "\n".join(f"- `{f['name']}`: {f['description']}" for f in data["functions"])

    if section == "categories":
        return ", ".join(f"{c['n']} {c['id']}" for c in data["categories"])

    if section == "mcp":
        m = data["mcp"]

        return "\n".join(
            f"- **{k.capitalize()}:** {_code(m[k])}" for k in ("tools", "prompts", "resources")
        )

    if section == "sets":
        return str(data["sets"]["note"])

    raise ValueError(f"unknown surface section {section!r}; choose from {SECTIONS}")


def markdown(data: dict[str, Any], names: tuple[str, ...] = SECTIONS) -> str:
    return "\n\n".join(f"## {n}\n\n{render(n, data)}" for n in names)


def region(name: str) -> re.Pattern[str]:
    return re.compile(rf"(<!-- surface:{name} -->\n)(.*?)(\n<!-- /surface:{name} -->)", re.DOTALL)


def sync(path: Path, data: dict[str, Any], write: bool = True) -> list[str]:
    """Rewrite every surface region in a markdown file. Returns the sections that were stale."""
    text = path.read_text(encoding="utf-8")
    stale = []

    for name in SECTIONS:
        match = region(name).search(text)

        if match and match.group(2) != render(name, data):
            stale.append(name)
            text = text[: match.start(2)] + render(name, data) + text[match.end(2) :]

    if stale and write:
        path.write_text(text, encoding="utf-8")

    return stale
