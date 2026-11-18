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
from clarity.matchers import dependency, phrase, structural
from clarity.matchers.common import CharSpan, sentences
from clarity.metrics import Analysis
from clarity.nlp import get_nlp
from clarity.positions import Units
from clarity.prose_metrics import report as prose_metrics_report
from clarity.readability import report as readability_report
from clarity.scoring import category_result, rule_over, score_document
from clarity.structure import Structure, coerce, parse_doc

SOURCE_STDIN = "<stdin>"
MAX_CHARS = 1_000_000


class InputError(ValueError):
    """Raised when the input cannot be analyzed, for example because it is too large."""
CONTEXT_LIMIT = 240


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


def _disabled(cfg: Config, s: Structure) -> list[dict[str, str]]:
    """Section rules need sections the caller stated: on a plain string, name them instead of
    reporting silent zeros."""
    if s.tree:
        return []

    reason = "the input is a plain string, not a section tree, so this rule is inert"

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


def _whole_field(text: str, s: Structure | None, start: int, end: int) -> bool:
    """The match covers its whole block (title, subtitle, paragraph or item), apart from
    surrounding whitespace and closing punctuation."""
    block = s.block_at(start) if s is not None else None
    lo, hi = (block.start, block.end) if block is not None else (0, len(text))

    return not text[lo:start].strip() and not text[end:hi].strip(" \t\n.:;!?")


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
        **({"remediation": rule.remediation} if rule.remediation else {}),
    }


def _candidates(
    rule: Rule, ctx: structural.Context, units: Units, cfg: Config, source: str, text: str,
    accepted: set[str],
) -> list[Cand]:  # fmt: skip
    doc = ctx.analysis.doc if ctx.analysis else None
    assert doc is not None
    out: list[Cand] = []

    s = ctx.analysis.structure if ctx.analysis else None

    for hit in _rule_hits(doc, rule, ctx):
        start, end = hit

        while start < end and text[start].isspace():
            start += 1  # a match that opens on the blank line between blocks starts at its text

        start, end = s.clip(start, end) if s is not None and s.tree else (start, end)

        if rule.params.get("whole_field") and not _whole_field(text, s, start, end):
            continue

        if s is not None and s.field_kind(start) not in rule.applies_to:
            continue

        tokens = doc.char_span(start, end, alignment_mode="expand")

        if tokens is None or not units.keep(rule.position, tokens):
            continue

        found = _finding(rule, cfg, source, text, start, end, _context(doc, text, start, end))

        if is_accepted(found["id"], accepted):
            continue

        found["message"] = ctx.messages.pop((rule.id, *hit), rule.message)
        detail = ctx.details.pop((rule.id, *hit), None)

        if detail:
            found["message"] = f"{found['message']} {detail}"
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
            and (not rule.requires_any
                 or sum(met(m) for m in rule.requires_any) >= rule.min_any)
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


def parse(text: str | dict[str, Any] | Structure, config: Config | None = None) -> Analysis:
    """One spaCy parse of the document, as an Analysis that metrics and records share."""
    s = coerce(text)

    return Analysis(parse_doc(get_nlp(), s), s.text, settings=_settings(config), structure=s)


def _settings(config: Config | None) -> dict[str, Any]:
    return {"topics": config.topics, "records": config.records} if config else {}


def analyze(
    text: str | dict[str, Any] | Structure,
    source: str = SOURCE_STDIN,
    config: Config | None = None,
    min_confidence: str = "inferred",
    accepted: set[str] | None = None,
    trace: bool = False,
) -> dict[str, Any]:
    """Findings, per-part scores and the document score. text is a plain string (one part) or a
    document tree (see clarity.structure)."""
    s = coerce(text)

    if len(s.text) > MAX_CHARS:
        raise InputError(
            f"input is too large: {len(s.text):,} characters, the limit is {MAX_CHARS:,}. "
            "Split the document and check the parts separately."
        )

    cfg = config or load_config(None)
    accepted = accepted or set()
    nlp = get_nlp()
    text = s.text
    doc = parse_doc(nlp, s)
    clause_list = clauses(doc)
    sections = s.sections()
    analysis = Analysis(doc, text, settings=_settings(cfg), structure=s)
    units = Units(doc, s.body_blocks(), sections, clause_list)
    ctx = structural.Context(
        nlp,
        sections,
        clauses=clause_list,
        clause_of=units.clause_of,
        paragraphs=s.paragraphs(),
        analysis=analysis,
    )
    disabled = _disabled(cfg, s)
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

    words = {p.index: s.words(doc, p.index) for p in s.parts}
    findings: list[dict[str, Any]] = []
    per_rule: dict[int, dict[str, dict[str, int]]] = {p.index: {} for p in s.parts}
    effective: dict[int, dict[str, Rule]] = {p.index: {} for p in s.parts}
    over_categories: dict[int, set[str]] = {p.index: set() for p in s.parts}

    def settle(rule: Rule) -> None:
        if rule.marker:
            return  # read by composites and in_scope above; never reported or scored

        by_part: dict[int, list[Cand]] = {}

        for c in pool.get(rule.id, []):
            by_part.setdefault(s.part_at(c.start), []).append(c)

        for part in s.parts:
            cands = by_part.get(part.index, [])
            shown = composition.allowance_override(rule, analysis, over_categories[part.index])
            eff = replace(rule, **shown[0]) if shown else rule
            effective[part.index][rule.id] = eff
            built = [c.finding for c in cands]
            unit_ids = [units.unit(rule.count_scope, c.tokens, c.start) for c in cands]
            over = _mark_over(eff, built, unit_ids, words[part.index])

            if shown:
                for f in built:
                    f["allowance_note"] = shown[1]

            if not rule.experimental:
                per_rule[part.index][rule.id] = {"found": len(built), "over": over}

                if over:
                    over_categories[part.index].add(cfg.categories[int(rule.category)].id)

            findings.extend(built)

    for rule in live:
        if not composition.gated_on_findings(rule):
            settle(rule)

    for rule in live:
        if composition.gated_on_findings(rule):
            settle(rule)

    parts = []

    for part in s.parts:
        cats = _categories(cfg, per_rule[part.index], words[part.index], effective[part.index])
        parts.append({"categories": cats, "score": round(score_document(cats), 1),
                      "words": words[part.index],
                      **(_text_measures(doc, part, cfg) if s.tree else {})})  # fmt: skip

    findings.sort(key=lambda f: (f["span"]["start"], f["rule"]))

    for f in findings:
        _place(f, s)

    total = sum(words.values())
    result = {
        "findings": findings,
        "categories": _merge_categories([p["categories"] for p in parts], list(words.values())),
        "score": _rollup(s, parts, 0)[0],
        "words": total,
        "sentences": len(sentences(doc)),
        "readability": readability_report(doc, cfg.readability),
        "prose_metrics": prose_metrics_report(analysis, cfg.prose_metrics),
        "disabled_rules": disabled,
    }

    result["section"] = _section_tree(s, parts, findings, 0)

    if trace:
        result["trace"] = notes

    return result


def _place(f: dict[str, Any], s: Structure) -> None:
    """Rewrite a finding's location into the caller's terms: the section path, the field, and
    offsets, line and column inside that field. A plain string is one field, so nothing moves."""
    start, end = int(f["span"]["start"]), int(f["span"]["end"])
    where = s.locate(start, end)
    f["span"].update(where["span"])
    f["line"], f["col"] = where["line"], where["col"]

    f["section"] = s.parts[s.part_at(start)].path
    f["field"] = where["field"]

    for child in f.get("children", []):
        _place(child, s)


def _text_measures(doc: Doc, part: Any, cfg: Config) -> dict[str, Any]:
    """Readability and prose metrics over a section's own text paragraphs. Titles, subtitles
    and items are fragments, so a section without text gets neither."""
    text_blocks = [b for b in part.blocks if b.field == "text"]

    if not text_blocks:
        return {}

    span = doc.char_span(text_blocks[0].start, text_blocks[-1].end, alignment_mode="expand")

    if span is None:
        return {}

    sub = span.as_doc()
    analysis = Analysis(sub, sub.text, settings={})

    return {"readability": readability_report(sub, cfg.readability),
            "prose_metrics": prose_metrics_report(analysis, cfg.prose_metrics)}  # fmt: skip


def _rollup(s: Structure, parts: list[dict[str, Any]], index: int) -> tuple[float, int]:
    """Word-weighted score of a part and everything under it, and the words that weigh it."""
    pairs = [(parts[index]["score"], parts[index]["words"])]
    pairs += [_rollup(s, parts, c) for c in s.parts[index].children]
    weight = sum(w for _, w in pairs)

    if not weight:
        return parts[index]["score"], 0

    return round(sum(sc * w for sc, w in pairs) / weight, 1), weight


def _section_tree(
    s: Structure, parts: list[dict[str, Any]], findings: list[dict[str, Any]], index: int
) -> dict[str, Any]:
    """The caller's tree, returned with each section's own findings, categories and scores."""
    p = s.parts[index]
    score, weight = _rollup(s, parts, index)
    node: dict[str, Any] = {"path": p.path}

    if p.id is not None:
        node["id"] = p.id

    if p.title is not None:
        node["title"] = p.title

    measures: dict[str, Any] = {
        k: parts[index][k] for k in ("readability", "prose_metrics") if k in parts[index]
    }
    node.update({
        "words": parts[index]["words"],
        "score": parts[index]["score"],
        "rollup": {"score": score, "words": weight},
        "findings": [f for f in findings if f["section"] == p.path],
        "categories": [c for c in parts[index]["categories"] if c["found"]],
        **measures,
        "sections": [_section_tree(s, parts, findings, c) for c in p.children],
    })  # fmt: skip

    return node


def _merge_categories(
    per_part: list[list[dict[str, Any]]], words: list[int]
) -> list[dict[str, Any]]:
    """Document-level categories: counts summed, penalty word-weighted across parts."""
    if len(per_part) == 1:
        return per_part[0]

    total = sum(words) or 1
    out = []

    for rows in zip(*per_part, strict=True):
        merged = dict(rows[0])

        for key in ("found", "over_by"):
            merged[key] = sum(r[key] for r in rows)

        merged["penalty"] = round(sum(r["penalty"] * w for r, w in zip(rows, words, strict=True))
                                  / total, 2)  # fmt: skip
        merged["allowance"] = round(sum(r["allowance"] for r in rows), 2)
        merged["capped"] = any(r["capped"] for r in rows)
        merged["rate_per_1k"] = round(merged["found"] * 1000 / total, 2)
        out.append(merged)

    return out


def short_section_factor(cfg: Config, words: int) -> float:
    """How much a short section's penalties are raised: min_section_words / words, between 1 and
    max_section_factor.

    Penalties count findings, so four tics cost a 40-word slide what they cost a 1,000-word essay.
    Scoring a short section as if its density held over min_section_words fixes that. The upper
    bound keeps a one-line input from hitting every category cap on its first finding.
    """
    floor = float(cfg.scoring.get("min_section_words") or 0)
    most = float(cfg.scoring.get("max_section_factor") or 1)

    return min(most, max(1.0, floor / words)) if words and floor else 1.0


def _categories(
    cfg: Config, per_rule: dict[str, dict[str, int]], words: int, effective: dict[str, Rule]
) -> list[dict[str, Any]]:
    out = []

    for n in sorted(cfg.categories):
        cat = cfg.categories[n]
        rules = [effective.get(r.id, r) for r in cfg.rules if int(r.category) == n]
        found = sum(per_rule.get(r.id, {}).get("found", 0) for r in rules)
        over = sum(per_rule.get(r.id, {}).get("over", 0) for r in rules)
        weighted = short_section_factor(cfg, words) * sum(
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


CONTRACT_KEYS = ("score", "words", "sentences", "section", "readability", "prose_metrics",
                 "disabled_rules")  # fmt: skip


def _without_source(finding: dict[str, Any]) -> dict[str, Any]:
    """Copy a finding without `source`. Composite children lose it too."""
    out = {k: v for k, v in finding.items() if k != "source"}

    if "children" in out:
        out["children"] = [_without_source(c) for c in out["children"]]

    return out


def _section_without_source(section: dict[str, Any]) -> dict[str, Any]:
    out = dict(section)
    out["findings"] = [_without_source(f) for f in section.get("findings", [])]
    out["sections"] = [_section_without_source(c) for c in section.get("sections", [])]

    return out


def contract(result: dict[str, Any]) -> dict[str, Any]:
    """The response clients get: the document score and the section tree. Each finding appears
    once, in the section where it was found. The section path and field locate a finding, so the
    response omits `source`."""
    out = {k: result[k] for k in CONTRACT_KEYS if k in result}

    if "section" in out:
        out["section"] = _section_without_source(out["section"])

    return out
