"""Text and JSON output."""

from __future__ import annotations

import json
from typing import Any

RESET = "\x1b[0m"
STYLES = {
    "error": "\x1b[31m",
    "warning": "\x1b[33m",
    "info": "\x1b[34m",
    "dim": "\x1b[2m",
    "bold": "\x1b[1m",
    "inferred": "\x1b[36m",
    "exact": "\x1b[35m",
}


def paint(text: str, style: str, color: bool) -> str:
    return f"{STYLES[style]}{text}{RESET}" if color else text


def render_json(result: dict[str, Any], source: str) -> str:
    return json.dumps({"source": source, **result}, indent=2, ensure_ascii=False)


def _finding_line(f: dict[str, Any], color: bool) -> list[str]:
    where = f"{f['source']}:{f['line']}:{f['col']}"
    tag = "allowed" if not f["over_allowance"] else f["severity"]
    conf = paint(f["confidence"], f["confidence"], color)
    head = f"  {where}  {paint(tag, tag if tag in STYLES else 'dim', color)} {conf} {f['rule']}"
    lines = [head, f"    {f['message']}"]

    if f["context"]:
        lines.append(paint(f"    > {f['context']}", "dim", color))

    return lines


def render_text(result: dict[str, Any], source: str, color: bool) -> str:
    out: list[str] = []
    by_cat: dict[str, list[dict[str, Any]]] = {}

    for f in result["findings"]:
        by_cat.setdefault(f["category"], []).append(f)

    for cat in result["categories"]:
        if not cat["found"]:
            continue

        allowed = cat["found"] - cat["over_by"]
        counts = f"{cat['found']} found · {allowed} allowed · over by {cat['over_by']}"
        header = f"{cat['name']}  {counts}"
        out.append(paint(header, "bold", color))

        for f in by_cat.get(cat["id"], []):
            out.extend(_finding_line(f, color))

        out.append("")

    out.append(f"Score: {result['score']:g}/100  ({result['words']} words, {source})")
    out.append(_readability_line(result["readability"]))

    return "\n".join(out)


def _readability_line(r: dict[str, Any]) -> str:
    low, high = r["target_grade"]
    state = "inside" if r["inside_band"] else "outside"
    fre = r["metrics"]["flesch_reading_ease"]

    return f"Readability: grade {r['grade']:g} ({state} band {low}-{high}), Flesch {fre:g}"
