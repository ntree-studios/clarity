"""Allowance arithmetic and document scoring."""

from typing import Any


def rule_over(found: int, words: int, max_per_1k: float) -> int:
    """Instances beyond the allowance. The allowance is floored for the document length."""
    allowed = int(max_per_1k * words / 1000) if words else 0

    return max(0, found - allowed)


def category_result(
    cat_id: str,
    name: str,
    found: int,
    words: int,
    max_per_1k: float,
    weight: float,
    cap: float,
    over_by: int | None = None,
    weighted_over: float | None = None,
) -> dict[str, Any]:
    """Build one category result.

    The allowance scales with document length; only the excess is penalized.
    """
    if over_by is None:
        over_by = rule_over(found, words, max_per_1k)

    rate = round(found * 1000 / words, 2) if words else 0.0
    raw = (over_by if weighted_over is None else weighted_over) * weight
    penalty = min(raw, cap)

    return {
        "id": cat_id,
        "name": name,
        "found": found,
        "max_per_1k": max_per_1k,
        "over_by": over_by,
        "rate_per_1k": rate,
        "penalty": penalty,
        "capped": raw > cap,
    }


def score_document(categories: list[dict[str, Any]]) -> float:
    total = sum(c["penalty"] for c in categories)

    return max(0.0, 100.0 - total) if categories else 100
