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
        "readability": cfg.readability,
        "prose_metrics": cfg.prose_metrics,
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


def init(stdout: TextIO) -> int:
    """Populate the user directory with the default pack and example profiles."""
    target = user_dir()
    pack = resources.files("clarity")
    text = pack.joinpath("default.yml").read_text(encoding="utf-8")
    head, _, rules = text.partition("\nrules:\n")
    files = {
        "clarity.yml": head.rstrip("\n") + "\n\n# profile: technical\n",
        "rules/default.yml": "rules:\n" + rules,
        "watchlist.yml": WATCHLIST_STARTER,
    }

    for source in sorted(pack.joinpath("profiles").iterdir(), key=lambda p: p.name):
        files[f"profiles/{source.name}"] = source.read_text(encoding="utf-8")

    for fixture in sorted(pack.joinpath("rules").iterdir(), key=lambda p: p.name):
        if fixture.name.endswith(".test.yml"):
            files[f"rules/{fixture.name}"] = fixture.read_text(encoding="utf-8")

    for source in sorted(pack.joinpath("examples").iterdir(), key=lambda p: p.name):
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
    return explain(resolved, rule_id)


def validate(resolved: Resolved) -> str:
    cfg = resolved.config

    counts = (len(cfg.rules), len(cfg.categories), len(resolved.files))

    return "ok: {} rules, {} categories, {} files".format(*counts)


__all__ = ["Path", "explain_rule", "init", "render", "summary", "validate"]
