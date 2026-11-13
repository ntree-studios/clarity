"""Text and JSON output."""

from __future__ import annotations

import json
from typing import Any

from clarity import baseline

RESET = "\x1b[0m"
STYLES = {
    "error": "\x1b[31m",
    "warning": "\x1b[33m",
    "info": "\x1b[34m",
    "dim": "\x1b[2m",
    "bold": "\x1b[1m",
    "inferred": "\x1b[36m",
    "exact": "\x1b[31m",
}
EXACT_OVER, INFERRED_OVER, WITHIN = "●", "◐", "○"
RULE_WIDTH = 72
POS_WIDTH = 7
SNIPPET_WIDTH = 46
TAG_WIDTH = 24
CATEGORY_WIDTH = 42
QUOTED_CATEGORIES = {"corporate-vocabulary", "watchlist"}


def paint(text: str, style: str, color: bool) -> str:
    return f"{STYLES[style]}{text}{RESET}" if color else text


def render_json(result: dict[str, Any], source: str) -> str:
    data = {k: v for k, v in result.items() if k not in {"config_line", "profile_line"}}

    return json.dumps({"source": source, **data}, indent=2, ensure_ascii=False)


def _marker(f: dict[str, Any]) -> tuple[str, str]:
    if not f["over_allowance"]:
        return WITHIN, "dim"

    if f["confidence"] == "inferred":
        return INFERRED_OVER, "inferred"

    return EXACT_OVER, "exact"


def _ellipsize(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3].rstrip() + "..."


def _snippet(f: dict[str, Any]) -> str:
    """The matched text with a little context, ellipsized where it was cut."""
    context, match = f["context"], " ".join(f["span"]["text"].split())
    at = context.find(match)

    if at < 0:
        return _ellipsize(match, SNIPPET_WIDTH - 2)  # the match spans sentences

    lead, tail = max(0, at - 14), min(len(context), at + len(match) + 14)
    text = ("..." if lead else "") + context[lead:tail] + ("..." if tail < len(context) else "")

    return _ellipsize(text, SNIPPET_WIDTH - 2)


def _tag(f: dict[str, Any]) -> str:
    term = " ".join(f["span"]["text"].split())

    if f["category"] in QUOTED_CATEGORIES and len(term.split()) == 1:
        return f'"{term.lower()}"'

    return str(f["rule"])


def _finding_lines(f: dict[str, Any], color: bool) -> list[str]:
    mark, style = _marker(f)
    pos = f"{f['line']}:{f['col']}"
    snippet, tag = f"{_snippet(f):<{SNIPPET_WIDTH}}", f"{_tag(f):<{TAG_WIDTH}}"
    gap = " " * (1 if len(pos) >= POS_WIDTH else 0)
    lines = [f"  {paint(mark, style, color)}  {pos:<{POS_WIDTH}}{gap}{snippet}{tag}[{f['id'][:6]}]"]
    note = f.get("detail") or (f["message"] if f["confidence"] == "inferred" else "")

    if note:
        lines.append(paint(f"            {note}", "dim", color))

    return lines


def _category_block(cat: dict[str, Any], found: list[dict[str, Any]], color: bool) -> list[str]:
    allowed = cat["found"] - cat["over_by"]
    state = "ok" if cat["over_by"] == 0 else f"over by {cat['over_by']}"
    counts = f"{cat['found']} found · {allowed} allowed · {state}"
    out = [paint(f"{cat['name'].upper():<{CATEGORY_WIDTH}}{counts}", "bold", color)]

    for f in found:
        out.extend(_finding_lines(f, color))

    out.append("")

    return out


def _ease_label(score: float) -> str:
    for floor, label in ((90, "very easy"), (80, "easy"), (70, "fairly easy"), (60, "standard"),
                         (50, "fairly difficult"), (30, "difficult")):  # fmt: skip
        if score >= floor:
            return label

    return "very difficult"


def _readability_block(r: dict[str, Any]) -> list[str]:
    low, high = r["target_grade"]
    m = r["metrics"]
    grade = m["flesch_kincaid_grade"]
    flag = "\u2190 above band" if grade > high else "\u2190 below band" if grade < low else ""
    flag = "" if r["inside_band"] is None else flag
    target = f"target grade {low}-{high}" if r["inside_band"] is not None else "band off"
    ease = m["flesch_reading_ease"]
    rows = [
        ("Flesch Reading Ease", ease, f"({_ease_label(ease)})"),
        ("Flesch-Kincaid Grade", grade, flag),
        ("Gunning Fog", m["gunning_fog"], ""),
        ("SMOG", m["smog"], ""),
        ("Coleman-Liau", m["coleman_liau"], ""),
        ("Automated Readability", m["ari"], ""),
    ]
    out = [f"{'READABILITY':<{RULE_WIDTH - 24}}{target}"]
    out.extend(f"  {name:<26}{value:>5.1f}   {note}".rstrip() for name, value, note in rows)

    return out


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{value:g}"


def _prose_metrics_block(block: dict[str, Any]) -> list[str]:
    m = block["metrics"]
    rows = []

    if "sentence_length_variance" in m:
        v = m["sentence_length_variance"]
        rows.append(("Sentence length", f"mean {_fmt(v['mean'])}, sd {_fmt(v['sd'])}"))

    if "paragraph_length_distribution" in m:
        v = m["paragraph_length_distribution"]
        detail = f"{v['count']}, mean {_fmt(v['mean'])} words, sd {_fmt(v['sd'])}"
        rows.append(("Paragraphs", detail))

    if "lexical_diversity" in m:
        rows.append(("Lexical diversity (MTLD)", _fmt(m["lexical_diversity"]["mtld"])))

    if "content_word_ratio" in m:
        rows.append(("Content / function words", _fmt(m["content_word_ratio"]["ratio"])))

    if "given_new_ordering" in m:
        v = m["given_new_ordering"]
        share = f"{_fmt(v['proportion'])} of {v['evaluated']} sentences"
        rows.append(("Given-new ordering", share))

    if "referential_density" in m:
        v = m["referential_density"]
        gap = _fmt(v["mean_antecedent_distance"])
        rows.append(("Referential density", f"{_fmt(v['per_1k'])}/1k, antecedent {gap} tokens"))

    if "mean_concreteness" in m:
        rows.append(("Mean concreteness", _fmt(m["mean_concreteness"]["mean"])))

    if "novelty_rate" in m:
        v = m["novelty_rate"]
        lines = ", ".join(str(p["line"]) for p in v["lowest_paragraphs"]) or "none"
        rate = f"{_fmt(v['per_sentence'])} new lemmas/sentence, lowest at {lines}"
        rows.append(("Novelty rate", rate))

    out = ["PROSE METRICS (advisory, unscored)"]
    out.extend(f"  {name:<26}{value}" for name, value in rows)

    return out


def _score_block(result: dict[str, Any], fail_under: float) -> list[str]:
    verdict = "FAIL" if result["score"] < fail_under else "PASS"
    out = [
        "─" * RULE_WIDTH,
        f"{'STYLE SCORE   ' + format(result['score'], 'g') + ' / 100':<52}"
        f"{verdict} (--fail-under {fail_under:g})",
        "",
    ]
    rows = sorted((c for c in result["categories"] if c["found"]), key=lambda c: -c["penalty"])

    for c in rows:
        penalty = f"-{c['penalty']:g}" if c["penalty"] else "0"
        allowed: Any = c["found"] - c["over_by"]
        fractional = c.get("allowance") is not None and c["allowance"] != int(c["allowance"])
        allowed = f"{c['allowance']:.2f}" if fractional else allowed
        state = "capped" if c["capped"] else ("within" if c["over_by"] == 0 else "")
        name = c["id"].replace("-", " ")
        rate = f"{c['rate_per_1k']:.1f}/1k"
        out.append(f"  {name:<26}{penalty:<7}{rate:>9}   allowed {allowed}   {state}".rstrip())

    return out


def _footer(result: dict[str, Any]) -> list[str]:
    findings = result["findings"]
    within = sum(1 for f in findings if not f["over_allowance"])
    exact = sum(1 for f in findings if f["over_allowance"] and f["confidence"] == "exact")
    inferred = sum(1 for f in findings if f["over_allowance"] and f["confidence"] == "inferred")
    out = [
        f"{len(findings)} findings · {len(findings) - within} over allowance · {within} within",
        f"{EXACT_OVER} exact ({exact})   {INFERRED_OVER} inferred ({inferred})   "
        f"{WITHIN} within allowance ({within})",
        "",
        "Filter to exact only:  clarity check --min-confidence exact",
    ]

    if findings:
        out.append(f"Accept a finding:      clarity accept {findings[0]['id'][:6]}")

    return out


def render_text(result: dict[str, Any], source: str, color: bool, fail_under: float = 80.0) -> str:
    out = [f"{source}   {result['words']} words · {result.get('sentences', 0)} sentences"]
    header = [line for line in (result.get("config_line"), result.get("profile_line")) if line]
    out += [*header, ""]

    if result.get("disabled_rules"):
        names = ", ".join(d["rule"] for d in result["disabled_rules"])
        out += [f"notice: no markdown headings, so these section rules are disabled: {names}", ""]

    by_cat: dict[str, list[dict[str, Any]]] = {}

    for f in result["findings"]:
        by_cat.setdefault(f["category"], []).append(f)

    for cat in result["categories"]:
        if cat["found"]:
            out.extend(_category_block(cat, by_cat.get(cat["id"], []), color))

    out += _score_block(result, fail_under)
    out += ["", *_readability_block(result["readability"])]
    out += ["", *_prose_metrics_block(result["prose_metrics"])]

    if "drift" in result:
        out += ["", "DRIFT", *baseline.format_drift(result["drift"]).splitlines()]

    out += ["", *_footer(result)]

    return "\n".join(out)
