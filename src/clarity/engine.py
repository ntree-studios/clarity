"""Run every rule over a document and score the result."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from spacy.tokens import Doc, Span

from clarity import composition
from clarity.accept import is_accepted
from clarity.clauses import clauses
from clarity.config import Config, Rule, load_config
from clarity.ids import finding_id
from clarity.markdown import (
    has_headings,
    mask_code_blocks,
    mask_markup,
    prose_paragraphs,
    section_ranges,
)
from clarity.matchers import dependency, phrase, structural
from clarity.matchers.common import CharSpan, sentences
from clarity.metrics import Analysis
from clarity.nlp import get_nlp
from clarity.positions import Units
from clarity.prose_metrics import report as prose_metrics_report
from clarity.readability import report as readability_report
from clarity.scoring import category_result, rule_over, score_document

SOURCE_STDIN = "<stdin>"
MAX_CHARS = 1_000_000


class InputError(ValueError):
    """Raised when the input cannot be analyzed, for example because it is too large."""
CONTEXT_LIMIT = 240


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


def _inert(rule: Rule) -> bool:
    return rule.count_scope == "section" or rule.position == "section-final"


def _disabled(cfg: Config, text: str) -> list[dict[str, str]]:
    """Section rules cannot work on plain text: name them instead of reporting silent zeros."""
    if has_headings(text):
        return []

    reason = "no markdown headings: the input is one section, so this rule is inert"

    return [{"rule": r.id, "reason": reason} for r in cfg.rules if _inert(r)]


def _mark_over(rule: Rule, built: list[dict[str, Any]], units: list[int], words: int) -> int:
    """Flag findings beyond the allowance. Returns the total number over."""
    if rule.count_scope == "document":
        over = rule_over(len(built), words, rule.max_per_1k or 0)
        groups = {0: list(range(len(built)))}
    else:
        groups = {}

        for i, unit in enumerate(units):
            groups.setdefault(unit, []).append(i)

        over = 0

    allowed = rule.max_per_scope or 0

    for members in groups.values():
        if rule.count_scope == "document":
            beyond = members[len(members) - over :] if over else []
        else:
            beyond = members[allowed:]
            over += len(beyond)

        for i in beyond:
            built[i]["over_allowance"] = True

    return over


@dataclass
class Cand:
    """One match of one rule, before suppression, composition and allowance."""

    finding: dict[str, Any]
    tokens: Span

    @property
    def start(self) -> int:
        return int(self.finding["span"]["start"])


def _finding(
    rule: Rule, cfg: Config, source: str, text: str, start: int, end: int, ctx_text: str
) -> dict[str, Any]:
    line, col = _position(text, start)

    return {
        "id": finding_id(rule.id, f"{text[start:end]}|{ctx_text}"),
        "rule": rule.id,
        "category": cfg.categories[int(rule.category)].id,
        "severity": rule.severity,
        "confidence": rule.confidence,
        "message": rule.message,
        "source": source,
        "line": line,
        "col": col,
        "span": {"start": start, "end": end, "text": text[start:end]},
        "context": ctx_text,
        "over_allowance": False,
        **({"experimental": True} if rule.experimental else {}),
        **({"suggestion": rule.suggestion} if rule.suggestion else {}),
    }


def _candidates(
    rule: Rule, ctx: structural.Context, units: Units, cfg: Config, source: str, text: str,
    accepted: set[str],
) -> list[Cand]:  # fmt: skip
    doc = ctx.analysis.doc if ctx.analysis else None
    assert doc is not None
    out: list[Cand] = []

    for start, end in _rule_hits(doc, rule, ctx):
        tokens = doc.char_span(start, end, alignment_mode="expand")

        if tokens is None or not units.keep(rule.position, tokens):
            continue

        found = _finding(rule, cfg, source, text, start, end, _context(doc, text, start, end))

        if is_accepted(found["id"], accepted):
            continue

        detail = ctx.details.pop((rule.id, start, end), None)

        if detail:
            found["message"] = f"{rule.message} {detail}"
            found["detail"] = detail

        out.append(Cand(found, tokens))

    return out


def _suppressed_by(
    rule: Rule, cand: Cand, analysis: Analysis, units: Units, others: dict[str, list[Cand]]
) -> str | None:
    """The first suppress_if condition that holds for this match, described, or None."""
    for cond in rule.suppress_if:
        if "metric" in cond:
            holds, text_ = composition.metric_holds(analysis, cond)
            why = text_ if holds else None
        elif "near" in cond:
            why = composition.near_holds(cand.tokens, cond["near"], rule.id)
        else:
            body = cond["in_scope"]
            mine = units.unit(body["count_scope"], cand.tokens, cand.start)
            hit = any(
                units.unit(body["count_scope"], o.tokens, o.start) == mine
                for o in others.get(body["rule"], [])
            )
            why = f"{body['rule']} found in the same {body['count_scope']}" if hit else None

        if why:
            return why

    return None


def _composite(
    rule: Rule, pool: dict[str, list[Cand]], units: Units, cfg: Config, source: str, text: str,
    trace: dict[str, Any],
) -> tuple[list[Cand], set[int]]:  # fmt: skip
    """Composite matches: one per scope unit where the members agree. Returns the matches and the
    ids of the member candidates they subsume."""
    scope = rule.count_scope
    by_unit: dict[int, dict[str, list[Cand]]] = {}

    for rid in {m["rule"] for m in composition.members(rule)}:
        for c in pool.get(rid, []):
            unit = units.unit(scope, c.tokens, c.start)
            by_unit.setdefault(unit, {}).setdefault(rid, []).append(c)

    out: list[Cand] = []
    used: set[int] = set()

    for unit_id, present in sorted(by_unit.items()):
        counts = {rid: len(v) for rid, v in present.items()}

        def met(m: dict[str, Any], counts: dict[str, int] = counts) -> bool:
            return bool(counts.get(m["rule"], 0) >= m.get("min_count", 1))

        ok = (
            all(met(m) for m in rule.requires_all)
            and (not rule.requires_any or any(met(m) for m in rule.requires_any))
            and not any(met(m) for m in rule.requires_none)
        )
        trace.setdefault(rule.id, []).append({"unit": unit_id, "members": counts, "fired": ok})

        if not ok:
            continue

        kids = [c for rid, v in present.items() for c in v if rid not in
                {m["rule"] for m in rule.requires_none}]  # fmt: skip
        start = min(c.start for c in kids)
        end = max(int(c.finding["span"]["end"]) for c in kids)
        tokens = units.doc.char_span(start, end, alignment_mode="expand")

        if tokens is None:
            continue

        context = " ".join(text[start:end].split())[:CONTEXT_LIMIT]
        found = _finding(rule, cfg, source, text, start, end, context)
        names = ", ".join(sorted({c.finding["rule"] for c in kids}))
        found["detail"] = f"{rule.note} ({names})" if rule.note else names
        found["children"] = [c.finding for c in sorted(kids, key=lambda c: c.start)]
        out.append(Cand(found, tokens))
        used |= {id(c) for c in kids}

    return out, used


def analyze(
    text: str,
    source: str = SOURCE_STDIN,
    config: Config | None = None,
    min_confidence: str = "inferred",
    accepted: set[str] | None = None,
    trace: bool = False,
) -> dict[str, Any]:
    if len(text) > MAX_CHARS:
        raise InputError(
            f"input is too large: {len(text):,} characters, the limit is {MAX_CHARS:,}. "
            "Split the document and check the parts separately."
        )

    cfg = config or load_config(None)
    accepted = accepted or set()
    nlp = get_nlp()
    masked = mask_markup(text)
    scannable = mask_code_blocks(text)
    doc = nlp(masked)
    words = _count_words(doc)
    clause_list = clauses(doc)
    sections = section_ranges(scannable)
    analysis = Analysis(doc, masked, text)
    units = Units(doc, scannable, sections, clause_list)
    ctx = structural.Context(
        nlp,
        sections,
        clauses=clause_list,
        clause_of=units.clause_of,
        paragraphs=prose_paragraphs(scannable),
        analysis=analysis,
    )
    disabled = _disabled(cfg, scannable)
    off = {d["rule"] for d in disabled}
    notes: dict[str, Any] = {"suppressed": [], "inactive": [], "composites": {}}
    pool: dict[str, list[Cand]] = {}
    live: list[Rule] = []

    for rule in cfg.rules:
        if rule.id in off or (min_confidence == "exact" and rule.confidence != "exact"):
            continue

        why = composition.inactive_reason(rule, analysis)

        if why:
            notes["inactive"].append({"rule": rule.id, "reason": why})

            continue

        live.append(rule)

        if rule.backend != "composite":
            pool[rule.id] = _candidates(rule, ctx, units, cfg, source, text, accepted)

    raw = {rid: list(c) for rid, c in pool.items()}

    for rule in live:
        if not rule.suppress_if:
            continue

        kept = []

        for cand in pool.get(rule.id, []):
            why = _suppressed_by(rule, cand, analysis, units, raw)

            if why:
                notes["suppressed"].append(
                    {
                        "rule": rule.id,
                        "text": cand.finding["span"]["text"],
                        "line": cand.finding["line"],
                        "condition": why,
                    }
                )
            else:
                kept.append(cand)

        pool[rule.id] = kept

    for rule in live:
        if rule.backend != "composite":
            continue

        made, used = _composite(rule, pool, units, cfg, source, text, notes["composites"])
        pool[rule.id] = made

        for rid in {m["rule"] for m in composition.members(rule)}:
            pool[rid] = [c for c in pool.get(rid, []) if id(c) not in used]

    findings: list[dict[str, Any]] = []
    per_rule: dict[str, dict[str, int]] = {}
    effective: dict[str, Rule] = {}
    over_categories: set[str] = set()

    def settle(rule: Rule) -> None:
        cands = pool.get(rule.id, [])
        shown = composition.allowance_override(rule, analysis, over_categories)
        eff = replace(rule, **shown[0]) if shown else rule
        effective[rule.id] = eff
        built = [c.finding for c in cands]
        unit_ids = [units.unit(rule.count_scope, c.tokens, c.start) for c in cands]
        over = _mark_over(eff, built, unit_ids, words)

        if shown:
            for f in built:
                f["allowance_note"] = shown[1]

        if not rule.experimental:
            per_rule[rule.id] = {"found": len(built), "over": over}

            if over:
                over_categories.add(cfg.categories[int(rule.category)].id)

        findings.extend(built)

    for rule in live:
        if not composition.gated_on_findings(rule):
            settle(rule)

    for rule in live:
        if composition.gated_on_findings(rule):
            settle(rule)

    categories = _categories(cfg, per_rule, words, effective)
    findings.sort(key=lambda f: (f["span"]["start"], f["rule"]))
    result = {
        "findings": findings,
        "categories": categories,
        "score": round(score_document(categories), 1),
        "words": words,
        "sentences": len(sentences(doc)),
        "readability": readability_report(doc, cfg.readability),
        "prose_metrics": prose_metrics_report(analysis, cfg.prose_metrics),
        "disabled_rules": disabled,
    }

    if trace:
        result["trace"] = notes

    return result


def _categories(
    cfg: Config, per_rule: dict[str, dict[str, int]], words: int, effective: dict[str, Rule]
) -> list[dict[str, Any]]:
    out = []

    for n in sorted(cfg.categories):
        cat = cfg.categories[n]
        rules = [effective.get(r.id, r) for r in cfg.rules if int(r.category) == n]
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
            sum(r.max_per_1k or 0 for r in rules if r.count_scope == "document"),
            cat.weight,
            cat.cap,
            over_by=over,
            weighted_over=weighted,
        )
        result["allowance"] = round(
            sum(
                (r.max_per_1k or 0) * words / 1000
                for r in rules
                if r.count_scope == "document" and not r.experimental
            ),
            2,
        )
        out.append(result)

    return out
