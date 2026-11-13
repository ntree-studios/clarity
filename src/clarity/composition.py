"""Rule composition: conditions over metrics and findings, and the validation of them.

Composites, suppress_if, active_when and allowance_when all share one condition vocabulary and
one validator, so a reference that cannot resolve fails at load with the rule and the field.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from typing import Any

from spacy.tokens import Span

from clarity.config import COUNT_SCOPES, Category, ConfigError, Rule
from clarity.metrics import REGISTRY, Analysis, load_registry, scalar

OPS: dict[str, Callable[[Any, Any], bool]] = {
    "lt": operator.lt, "lte": operator.le, "gt": operator.gt, "gte": operator.ge,
    "eq": operator.eq,
}  # fmt: skip
GROUPS = ("requires_all", "requires_any", "requires_none")
NEAR_KEYS = ("pos", "lemma", "pattern", "ent")
SUPPRESS_KEYS = ("near", "in_scope")


class CompositionError(ConfigError):
    """A composition field that does not resolve. Carries the rule id for the source prefix."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(f"rule {rule_id}: {message}")
        self.rule_id = rule_id


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []

    return value if isinstance(value, list) else [value]


def members(rule: Rule) -> list[dict[str, Any]]:
    return [m for group in GROUPS for m in getattr(rule, group)]


def dependencies(rule: Rule) -> set[str]:
    """Rule ids this rule reads: composite members and in_scope suppressors."""
    ids = {m["rule"] for m in members(rule) if isinstance(m, dict) and "rule" in m}

    for cond in rule.suppress_if:
        if isinstance(cond, dict) and isinstance(cond.get("in_scope"), dict):
            ids.add(cond["in_scope"].get("rule"))

    return {i for i in ids if isinstance(i, str)}


def closure(rule: Rule, by_id: dict[str, Rule]) -> set[str]:
    """The rule and everything it needs, so one rule can be evaluated alone."""
    seen: set[str] = set()
    todo = [rule.id]

    while todo:
        rid = todo.pop()

        if rid in seen or rid not in by_id:
            continue

        seen.add(rid)
        todo.extend(dependencies(by_id[rid]))

    return seen


# ---- validation ---------------------------------------------------------------------------


def _metric_key(rule_id: str, cond: dict[str, Any], where: str) -> None:
    name = cond.get("metric")

    if name not in REGISTRY:
        raise CompositionError(rule_id, f"{where}: unknown metric {name!r}")

    if cond.get("op") not in OPS:
        raise CompositionError(rule_id, f"{where}: op must be one of {sorted(OPS)}")

    if not isinstance(cond.get("value"), int | float):
        raise CompositionError(rule_id, f"{where}: value must be a number")

    if not cond.get("key") and not REGISTRY[name].scalars:
        raise CompositionError(rule_id, f"{where}: metric {name} has no scalar, give a key")


def _validate_members(rule: Rule, by_id: dict[str, Rule]) -> None:
    for group in GROUPS:
        for m in getattr(rule, group):
            if not isinstance(m, dict) or "rule" not in m:
                raise CompositionError(rule.id, f"{group}: each member is {{rule, min_count?}}")

            target = by_id.get(m["rule"])

            if target is None:
                raise CompositionError(
                    rule.id, f"{group} refers to unknown or disabled rule {m['rule']!r}"
                )

            if target.id == rule.id:
                raise CompositionError(rule.id, f"{group} refers to the rule itself")

            if target.backend == "composite":
                raise CompositionError(
                    rule.id, f"{group} refers to composite {target.id!r}; composites cannot nest"
                )

            count = m.get("min_count", 1)

            if not isinstance(count, int) or count < 1:
                raise CompositionError(rule.id, f"{group}: min_count must be a whole number >= 1")

    if not rule.requires_all and not rule.requires_any:
        raise CompositionError(rule.id, "a composite needs requires_all or requires_any")


def _validate_suppress(rule: Rule, by_id: dict[str, Rule]) -> None:
    for n, cond in enumerate(rule.suppress_if):
        where = f"suppress_if[{n}]"

        if isinstance(cond, dict) and isinstance(cond.get("metric"), str):
            _metric_key(rule.id, cond, where)

            continue

        keys = [k for k in SUPPRESS_KEYS if isinstance(cond, dict) and k in cond]

        if len(keys) != 1 or len(cond) != 1:
            raise CompositionError(rule.id, f"{where}: use exactly one of {SUPPRESS_KEYS}")

        body = cond[keys[0]]

        if keys[0] == "near":
            chosen = [k for k in NEAR_KEYS if k in body]

            if len(chosen) != 1 or not isinstance(body.get("within"), int):
                raise CompositionError(
                    rule.id, f"{where}: near needs one of {NEAR_KEYS} and within"
                )

            if "pattern" in body:
                _compiled(rule.id, where, body["pattern"])
        else:
            other = by_id.get(body.get("rule"))

            if other is None or other.id == rule.id:
                raise CompositionError(
                    rule.id, f"{where}: in_scope.rule is unknown, disabled or self"
                )

            if body.get("count_scope") not in COUNT_SCOPES:
                raise CompositionError(
                    rule.id, f"{where}: count_scope must be one of {COUNT_SCOPES}"
                )


def _compiled(rule_id: str, where: str, pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise CompositionError(rule_id, f"{where}: bad pattern {pattern!r}: {exc}") from exc


def _validate_gates(rule: Rule, categories: dict[int, Category]) -> None:
    for n, cond in enumerate(_as_list(rule.active_when)):
        _metric_key(rule.id, cond, f"active_when[{n}]")

    slugs = {c.id for c in categories.values()}
    own = categories[int(rule.category)].id

    for n, cond in enumerate(rule.allowance_when):
        where = f"allowance_when[{n}]"
        field_ = "max_per_1k" if rule.count_scope == "document" else "max_per_scope"

        if field_ not in cond:
            raise CompositionError(rule.id, f"{where}: give {field_} (the rule's count_scope)")

        if "over_allowance" in cond:
            if cond["over_allowance"] not in slugs or cond["over_allowance"] == own:
                raise CompositionError(
                    rule.id, f"{where}: over_allowance must name another category, got "
                    f"{cond['over_allowance']!r}"  # fmt: skip
                )
        else:
            _metric_key(rule.id, cond, where)


def validate(rules: list[Rule], categories: dict[int, Category]) -> None:
    """Resolve every composition reference. Raises CompositionError with the rule id and field."""
    load_registry()
    by_id = {r.id: r for r in rules}

    for rule in rules:
        has = any(getattr(rule, g) for g in GROUPS)

        if rule.backend == "composite":
            _validate_members(rule, by_id)
        elif has:
            raise CompositionError(rule.id, "requires_* is only valid with backend: composite")

        _validate_suppress(rule, by_id)
        _validate_gates(rule, categories)


# ---- evaluation ---------------------------------------------------------------------------


def metric_value(analysis: Analysis, cond: dict[str, Any]) -> float | None:
    name = cond["metric"]
    key = cond.get("key") or REGISTRY[name].scalars[0]

    return scalar(analysis.get(name), key)


def metric_holds(analysis: Analysis, cond: dict[str, Any]) -> tuple[bool, str]:
    value = metric_value(analysis, cond)
    shown = "n/a" if value is None else f"{value:g}"
    text = f"{cond['metric']} {shown} {cond['op']} {cond['value']:g}"

    return value is not None and OPS[cond["op"]](value, cond["value"]), text


def inactive_reason(rule: Rule, analysis: Analysis) -> str | None:
    """Why active_when switches the rule off, or None when it applies."""
    for cond in _as_list(rule.active_when):
        holds, text = metric_holds(analysis, cond)

        if not holds:
            return f"active_when not met: {text}"

    return None


def allowance_override(
    rule: Rule, analysis: Analysis, over_categories: set[str]
) -> tuple[dict[str, Any], str] | None:
    """The first allowance_when entry that holds: (new allowance field, why)."""
    for cond in rule.allowance_when:
        field_ = "max_per_1k" if rule.count_scope == "document" else "max_per_scope"

        if "over_allowance" in cond:
            if cond["over_allowance"] in over_categories:
                return {field_: cond[field_]}, f"{cond['over_allowance']} is over its allowance"
        else:
            holds, text = metric_holds(analysis, cond)

            if holds:
                return {field_: cond[field_]}, text

    return None


def gated_on_findings(rule: Rule) -> bool:
    return any("over_allowance" in c for c in rule.allowance_when)


def near_tokens(span: Span, within: int) -> list[Any]:
    """Tokens within N tokens of the span, on either side, excluding the span."""
    doc = span.doc
    before = doc[max(0, span.start - within) : span.start]
    after = doc[span.end : min(len(doc), span.end + within)]

    return [*before, *after]


def near_holds(span: Span, body: dict[str, Any], rule_id: str) -> str | None:
    window = near_tokens(span, body["within"])

    if "pos" in body:
        wanted = set(_as_list(body["pos"]))
        hit = next((t for t in window if t.pos_ in wanted), None)

        return f"near pos {sorted(wanted)} within {body['within']} ({hit.text!r})" if hit else None

    if "ent" in body:
        wanted = set(_as_list(body["ent"]))
        hit = next((t for t in window if t.ent_type_ in wanted), None)

        return f"near ent {sorted(wanted)} within {body['within']} ({hit.text!r})" if hit else None

    if "lemma" in body:
        wanted = {str(x).lower() for x in _as_list(body["lemma"])}
        hit = next((t for t in window if t.lemma_.lower() in wanted), None)

        if not hit:
            return None

        return f"near lemma {sorted(wanted)} within {body['within']} ({hit.text!r})"

    pattern = _compiled(rule_id, "near.pattern", body["pattern"])
    doc = span.doc
    lo, hi = max(0, span.start - body["within"]), min(len(doc), span.end + body["within"])
    found = None

    for a, b in ((lo, span.start), (span.end, hi)):
        if a < b:
            found = pattern.search(doc.text[doc[a].idx : doc[b - 1].idx + len(doc[b - 1])])

        if found:
            break

    if not found:
        return None

    return f"near pattern {body['pattern']!r} within {body['within']} ({found.group(0)!r})"
