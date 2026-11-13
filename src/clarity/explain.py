"""clarity explain: why a rule did or did not match, token by token."""

from __future__ import annotations

from typing import Any

from spacy.tokens import Token

from clarity.config import Rule
from clarity.engine import analyze
from clarity.harness import focus
from clarity.nlp import get_nlp
from clarity.resolve import Resolved

TICK, CROSS = "✓", "✗"
LIST_SHOWN = 4


def _listed(values: list[Any]) -> str:
    shown = ", ".join(str(v) for v in values[:LIST_SHOWN])

    return f"[{shown}, ...]" if len(values) > LIST_SHOWN else f"[{shown}]"


def _attr(token: Token, name: str, want: Any) -> tuple[bool, str]:
    have = {
        "POS": token.pos_, "LEMMA": token.lemma_, "LOWER": token.lower_, "TEXT": token.text,
        "DEP": token.dep_, "TAG": token.tag_,
    }.get(name)  # fmt: skip

    if isinstance(want, dict) and "IN" in want:
        ok = have in want["IN"]
        words = _listed(want["IN"])

        return ok, f"in {name.lower()} set {words}" if ok else f"not in {name.lower()} set {words}"

    return have == want, f"matches {want}" if have == want else f"is {have}, wanted {want}"


def _token_ok(token: Token, spec: dict[str, Any]) -> tuple[bool, str]:
    reasons = []

    for name, want in spec.items():
        ok, why = _attr(token, name, want)

        if not ok:
            return False, why

        reasons.append(why)

    return True, "; ".join(reasons)


def _best_attempt(doc: Any, pattern: list[dict[str, Any]]) -> tuple[int, list[tuple[bool, str]]]:
    """The start token whose attempt gets furthest through the pattern."""
    best: tuple[int, list[tuple[bool, str]]] = (0, [])

    for start in range(len(doc)):
        steps: list[tuple[bool, str]] = []

        for offset, spec in enumerate(pattern):
            if start + offset >= len(doc):
                break

            steps.append(_token_ok(doc[start + offset], spec))

            if not steps[-1][0]:
                break

        done = sum(1 for ok, _ in steps if ok)

        if done > sum(1 for ok, _ in best[1] if ok):
            best = (start, steps)

    return best


def _member_state(m: dict[str, Any], counts: dict[str, int]) -> str:
    have, need = counts.get(m["rule"], 0), m.get("min_count", 1)

    return f"{m['rule']} {TICK if have >= need else CROSS} ({have} of {need})"


def _composition_lines(rule: Rule, trace: dict[str, Any]) -> list[str]:
    """Member states of a composite, the matches suppress_if removed, and an inactive gate."""
    out = [f"  INACTIVE · {i['reason']}" for i in trace["inactive"] if i["rule"] == rule.id]
    out += [f'  SUPPRESSED "{s["text"]}" at line {s["line"]} · {s["condition"]}'
            for s in trace["suppressed"] if s["rule"] == rule.id]  # fmt: skip

    if rule.backend != "composite":
        return out

    groups = [("all of", rule.requires_all), ("any of", rule.requires_any),
              ("none of", rule.requires_none)]  # fmt: skip
    rows = trace["composites"].get(rule.id, [])

    for row in rows:
        shown = [f"{label}: " + ", ".join(_member_state(m, row["members"]) for m in group)
                 for label, group in groups if group]  # fmt: skip
        verdict = "FIRES" if row["fired"] else "no match"
        out.append(f"  {rule.count_scope} {row['unit']}: " + " · ".join(shown) + f" → {verdict}")

    return out or ["  no member rule matched anywhere"]


def explain(rule: Rule, text: str, resolved: Resolved) -> str:
    doc = get_nlp()(text)
    result = analyze(text, config=focus(rule, resolved.config), trace=True)
    found = [f for f in result["findings"] if f["rule"] == rule.id]
    lines = [f"{rule.id} · backend: {rule.backend}", ""]
    marks: dict[int, str] = {}
    verdict = ""

    if rule.pattern:
        start, steps = _best_attempt(doc, rule.pattern)

        for offset, (ok, why) in enumerate(steps):
            marks[start + offset] = f"{TICK if ok else CROSS} {why}"

        failed = next((i for i, (ok, _) in enumerate(steps) if not ok), None)

        if failed is not None:
            verdict = f"NO MATCH · failed at token {failed + 1}"
        elif len(steps) < len(rule.pattern):
            verdict = "NO MATCH · the text ends before the pattern does"

    for tok in doc:
        mark = marks.get(tok.i, "")
        lines.append(f"  {tok.text:<14}{tok.pos_:<8}{tok.dep_:<10}{mark}".rstrip())

    lines.append("")
    lines += _composition_lines(rule, result["trace"])

    if found:
        for f in found:
            lines.append(f'  MATCH at {f["line"]}:{f["col"]} "{f["span"]["text"]}"')
    else:
        lines.append(f"  {verdict or 'NO MATCH'}")

        if rule.phrases and not rule.pattern:
            lines.append(f"  phrases tried: {_listed(rule.phrases)}")

    where = rule.position
    scope = rule.count_scope
    allowance = rule.max_per_1k if scope == "document" else rule.max_per_scope
    field_ = "max_per_1k" if scope == "document" else "max_per_scope"
    lines += [f"  position: {where}", f"  count_scope: {scope} · {field_}: {allowance}"]

    return "\n".join(lines)
