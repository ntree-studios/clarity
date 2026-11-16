"""clarity config and clarity init."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, TextIO

from clarity.resolve import Resolved, config_line, display, explain, profile_line, user_dir

WATCHLIST_STARTER = (
    "# User terms. Example:\n# watchlist:\n#   - {term: synergy, max_per_1k: 0}\nwatchlist: []\n"
)


def summary(resolved: Resolved) -> dict[str, Any]:
    cfg = resolved.config

    return {
        "config_sources": resolved.files,
        "profile": {"name": resolved.profile.name, "path": resolved.profile.path}
        if resolved.profile
        else None,
        "builtin": resolved.builtin,
        "profiles": [{"name": p.name, "path": p.path} for p in resolved.profiles.values()],
        "readability": cfg.readability,
        "prose_metrics": cfg.prose_metrics,
        "topics": cfg.topics,
        "categories": [
            {"n": n, "id": c.id, "weight": c.weight, "cap": c.cap}
            for n, c in sorted(cfg.categories.items())
        ],
        "rules": [
            {
                "id": r.id,
                "category": cfg.categories[int(r.category)].id,
                "count_scope": r.count_scope,
                "position": r.position,
                "max_per_1k": r.max_per_1k,
                "max_per_scope": r.max_per_scope,
                "severity": r.severity,
                "confidence": r.confidence,
                "experimental": r.experimental,
            }
            for r in cfg.rules
        ],
    }


def render(resolved: Resolved, fmt: str) -> str:
    data = summary(resolved)

    if fmt == "json":
        return json.dumps(data, indent=2)

    out = [config_line(resolved)]
    out += [line] if (line := profile_line(resolved)) else []
    out += ["", "PROFILES" + ("" if resolved.builtin else " (builtin: false)")]
    out += [f"  {p['name']:<24}{display(p['path'])}" for p in data["profiles"]] or ["  none"]
    out += ["", "CATEGORIES"]
    for c in data["categories"]:
        out.append(f"  {c['n']:>2} {c['id']:<24}weight {c['weight']:<5g} cap {c['cap']:g}")

    out += ["", f"RULES  {len(data['rules'])} active"]

    for r in data["rules"]:
        allowance = (
            f"max_per_1k {r['max_per_1k']:g}"
            if r["count_scope"] == "document"
            else f"max_per_scope {r['max_per_scope']:g} per {r['count_scope']}"
        )
        flag = "  experimental" if r["experimental"] else ""
        out.append(f"  {r['id']:<30}{r['category']:<22}{allowance}{flag}")

    return "\n".join(out)


def split_rules_by_category(rules: str) -> dict[str, str]:
    """Split the text under `rules:` into one block of rule entries per category.

    Works on text so the comments inside each rule survive. A rule starts at a two-space
    `- id:` line; its category comes from its first `category:` line.
    """
    blocks: list[list[str]] = []

    for line in rules.splitlines(keepends=True):
        if line.startswith("  - id:") or not blocks:
            blocks.append([])

        blocks[-1].append(line)

    grouped: dict[str, str] = {}

    for block in blocks:
        category = next(
            (ln.split(":", 1)[1].strip() for ln in block if ln.strip().startswith("category:")),
            "default",
        )
        grouped[category] = grouped.get(category, "") + "".join(block)

    return grouped


def init(stdout: TextIO) -> int:
    """Populate the user directory: the default rules split by category, and starter profiles."""
    target = user_dir()
    pack = resources.files("clarity")
    text = pack.joinpath("default.yml").read_text(encoding="utf-8")
    head, _, rules = text.partition("\nrules:\n")
    files = {
        "clarity.yml": head.rstrip("\n") + "\n\n# profile: technical\n",
        "watchlist.yml": WATCHLIST_STARTER,
    }

    for category, body in split_rules_by_category(rules).items():
        files[f"rules/{category}.yml"] = "rules:\n" + body

    profiles = pack.joinpath("examples").joinpath("profiles")

    for source in sorted(profiles.iterdir(), key=lambda p: p.name):
        files[f"profiles/{source.name}"] = source.read_text(encoding="utf-8")

    for fixture in sorted(pack.joinpath("rules").iterdir(), key=lambda p: p.name):
        if fixture.name.endswith(".test.yml"):
            files[f"rules/{fixture.name}"] = fixture.read_text(encoding="utf-8")

    for source in sorted(pack.joinpath("examples").iterdir(), key=lambda p: p.name):
        if not source.is_file():
            continue

        files[f"examples/{source.name}"] = source.read_text(encoding="utf-8")

    written = skipped = 0

    for name, content in files.items():
        path = target / name

        if path.exists():
            skipped += 1

            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written += 1

    stdout.write(f"{display(str(target))}: {written} files written, {skipped} already present\n")

    return 0


def explain_rule(resolved: Resolved, rule_id: str) -> str:
    if rule_id == "topics" or rule_id.startswith("topics."):
        return explain_topics(resolved, rule_id)

    return explain(resolved, rule_id)


def explain_topics(resolved: Resolved, scope: str = "topics") -> str:
    """Every effective topics setting with the files that set it, nearest last."""
    settings = resolved.config.topics
    prov = resolved.provenance
    lines = [scope]

    def row(key: str, value: Any, events: list[tuple[str, str, str]]) -> None:
        sources = " → ".join(display(src) for src, _, _ in events) or "default"
        lines.append(f"  {key:<30}{json.dumps(value):<22}{sources}")

    for group, value in settings.items():
        name = f"topics.{group}"

        if not name.startswith(scope) and not scope.startswith(name):
            continue

        if isinstance(value, dict) and group != "named":
            for leaf, leaf_value in value.items():
                if f"{name}.{leaf}".startswith(scope):
                    row(f"{group}.{leaf}", leaf_value, prov.get(name, {}).get(leaf, []))
        elif group == "named":
            events = [e for evs in prov.get(name, {}).values() for e in evs]
            row(group, value, events)
        else:
            row(group, value, prov.get("topics", {}).get(group, []))

    return "\n".join(lines)


def validate(resolved: Resolved) -> str:
    cfg = resolved.config

    counts = (len(cfg.rules), len(cfg.categories), len(resolved.files))

    return "ok: {} rules, {} categories, {} files".format(*counts)


__all__ = ["Path", "explain_rule", "init", "render", "summary", "validate"]
