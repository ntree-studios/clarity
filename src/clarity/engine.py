"""Run every rule over a document and score the result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spacy.tokens import Doc

from clarity.config import Config, Rule, load_config
from clarity.ids import finding_id
from clarity.markdown import mask_headings, section_ranges
from clarity.matchers import dependency, phrase, structural
from clarity.matchers.common import CharSpan
from clarity.nlp import get_nlp
from clarity.readability import report as readability_report
from clarity.scoring import category_result, rule_over, score_document

SOURCE_STDIN = "<stdin>"
CONTEXT_LIMIT = 240


@dataclass
class _Hit:
    rule: Rule
    start: int
    end: int


def _count_words(doc: Doc) -> int:
    return sum(1 for t in doc if not t.is_punct and not t.is_space)


def _rule_hits(doc: Doc, rule: Rule, ctx: structural.Context) -> list[CharSpan]:
    nlp = ctx.nlp

    if rule.backend == "phrase":
        return phrase.run(doc, rule, nlp, phrase.build_matcher(nlp, rule))

    if rule.backend == "dependency":
        return dependency.run(doc, rule, nlp, dependency.build_matcher(nlp, rule))

    return structural.run(doc, rule, ctx)


def _context(doc: Doc, text: str, start: int, end: int) -> str:
    span = doc.char_span(start, end, alignment_mode="expand")
    sent = span.sent.text if span is not None else text[start:end]

    return " ".join(sent.split())[:CONTEXT_LIMIT]


def _position(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1

    return line, col


def analyze(
    text: str,
    source: str = SOURCE_STDIN,
    config: Config | None = None,
    min_confidence: str = "inferred",
    accepted: set[str] | None = None,
) -> dict[str, Any]:
    cfg = config or load_config(None)
    accepted = accepted or set()
    nlp = get_nlp()
    doc = nlp(mask_headings(text))
    words = _count_words(doc)
    ctx = structural.Context(nlp, section_ranges(text))
    findings: list[dict[str, Any]] = []
    per_rule: dict[str, dict[str, int]] = {}

    for rule in cfg.rules:
        if min_confidence == "exact" and rule.confidence != "exact":
            continue

        built: list[dict[str, Any]] = []

        for start, end in _rule_hits(doc, rule, ctx):
            ctx_text = _context(doc, text, start, end)
            fid = finding_id(rule.id, f"{text[start:end]}|{ctx_text}")

            if fid in accepted:
                continue

            detail = ctx.details.pop((rule.id, start, end), None)
            message = f"{rule.message} {detail}" if detail else rule.message
            line, col = _position(text, start)
            built.append(
                {
                    "id": fid,
                    "rule": rule.id,
                    "category": cfg.categories[int(rule.category)].id,
                    "severity": rule.severity,
                    "confidence": rule.confidence,
                    "message": message,
                    "source": source,
                    "line": line,
                    "col": col,
                    "span": {"start": start, "end": end, "text": text[start:end]},
                    "context": ctx_text,
                    "over_allowance": False,
                    **({"suggestion": rule.suggestion} if rule.suggestion else {}),
                }
            )

        over = rule_over(len(built), words, rule.max_per_1k)
        allowed = len(built) - over

        for f in built[allowed:]:
            f["over_allowance"] = True

        per_rule[rule.id] = {"found": len(built), "over": over}
        findings.extend(built)

    categories = _categories(cfg, per_rule, words)
    findings.sort(key=lambda f: (f["span"]["start"], f["rule"]))

    return {
        "findings": findings,
        "categories": categories,
        "score": round(score_document(categories), 1),
        "words": words,
        "readability": readability_report(doc, cfg.readability),
    }


def _categories(
    cfg: Config, per_rule: dict[str, dict[str, int]], words: int
) -> list[dict[str, Any]]:
    out = []

    for n in sorted(cfg.categories):
        cat = cfg.categories[n]
        rules = [r for r in cfg.rules if int(r.category) == n]
        found = sum(per_rule.get(r.id, {}).get("found", 0) for r in rules)
        over = sum(per_rule.get(r.id, {}).get("over", 0) for r in rules)
        weighted = sum(
            per_rule.get(r.id, {}).get("over", 0) * cfg.severity_weights.get(r.severity, 1.0)
            for r in rules
        )
        result = category_result(
            cat.id,
            cat.name,
            found,
            words,
            sum(r.max_per_1k for r in rules),
            cat.weight,
            cat.cap,
            over_by=over,
            weighted_over=weighted,
        )
        out.append(result)

    return out
