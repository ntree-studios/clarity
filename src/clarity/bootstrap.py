"""Bootstrap a rule pack from two folders of writing.

The AI client proposes; clarity measures. A rule is written only if this process measured that
exact definition against both corpora and its bad/good ratio met the floor.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import yaml
from spacy.lang.en.stop_words import STOP_WORDS

from clarity import baseline, composition, corpus
from clarity.accept import accept
from clarity.config import Config, Rule, load_config
from clarity.corpus import Size, documents, measure_size, require_floor
from clarity.engine import analyze
from clarity.fixtures import MIN_FIRE, MIN_NO_FIRE, Case, parse_case
from clarity.harness import check_fire, focus, hits
from clarity.metrics import load_registry
from clarity.resolve import (
    Resolved,
    discover_profiles,
    explain,
    find_project_dir,
    resolve,
    user_dir,
)

RATIO_FLOOR = 3.0
TOKEN = re.compile(r"[a-z][a-z']*")
SAMPLE_WIDTH = 60
RULES_FILE, FIXTURES_FILE = "bootstrap.yml", "bootstrap.test.yml"
SUGGEST_LIMIT = 50
METRICS = {
    "sentence_length_variance": "mean",
    "lexical_diversity": "mtld",
    "content_word_ratio": "ratio",
    "given_new_ordering": "proportion",
    "mean_concreteness": "mean",
    "novelty_rate": "per_sentence",
}


@dataclass
class Measurement:
    rule_id: str
    ratio: float | None
    bad_rate: float
    passes: bool


# Measurements made by this process, keyed by the exact rule definition. write_rules reads this.
MEASURED: dict[str, Measurement] = {}


def fingerprint(definition: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(definition, sort_keys=True, default=str).encode()).hexdigest()


def build_rule(definition: dict[str, Any]) -> tuple[Rule, Config]:
    """A rule from an unsaved definition, validated by the same loader that reads config files."""
    if not isinstance(definition, dict) or "id" not in definition:
        raise ValueError("a rule definition is an object with at least an id")

    proposed = {"rules": [{**definition, "experimental": True}]}
    config = resolve(None, Path.cwd(), None, extra=proposed).config
    rule = next(r for r in config.rules if r.id == definition["id"])

    return rule, config


def _resolved() -> Resolved:
    return resolve(None, Path.cwd(), None)


def _rule_by_id(rule_id: str) -> tuple[Rule, Config]:
    config = _resolved().config
    rule = next((r for r in config.rules if r.id == rule_id), None)

    if rule is None:
        raise ValueError(f"unknown rule {rule_id!r}")

    return rule, config


def _rule_for(rule_id: str | None, definition: dict[str, Any] | None) -> tuple[Rule, Config]:
    if definition is not None:
        return build_rule(definition)

    if rule_id is None:
        raise ValueError("give rule_id or rule_definition")

    return _rule_by_id(rule_id)


# ---- corpus_stats -------------------------------------------------------------------------


def _size_block(size: Size) -> dict[str, Any]:
    return {"path": size.path, "documents": size.documents, "words": size.words,
            "reliability": size.reliability}  # fmt: skip


def corpus_stats(path: str) -> dict[str, Any]:
    """Size, average prose metrics and per-rule hit rates under the loaded pack."""
    root = Path(path)
    size = measure_size(root)
    config = _resolved().config
    hit_counts: Counter[str] = Counter()
    metric_values: dict[str, list[float]] = {name: [] for name in METRICS}
    words = 0

    for file, text in documents(root):
        result = analyze(text, source=str(file), config=config)
        words += result["words"]
        hit_counts.update(f["rule"] for f in result["findings"])

        for name, key in METRICS.items():
            value = result["prose_metrics"]["metrics"].get(name, {}).get(key)

            if value is not None:
                metric_values[name].append(value)

    return {
        **_size_block(size),
        "prose_metrics": {
            name: round(statistics.fmean(v), 2) if v else None for name, v in metric_values.items()
        },
        "rule_hits_per_1k": {
            rule: round(n * 1000 / words, 2) for rule, n in hit_counts.most_common()
        }
        if words
        else {},
    }


# ---- test_rule and find_matches -----------------------------------------------------------


def _scan(rule: Rule, config: Config, root: Path, limit: int = 3) -> dict[str, Any]:
    docs = words = total = 0
    docs_hit = 0
    samples: list[dict[str, Any]] = []

    for file, text in documents(root):
        result = analyze(text, source=str(file), config=focus(rule, config))
        found = [f for f in result["findings"] if f["rule"] == rule.id]
        docs += 1
        words += result["words"]
        total += len(found)
        docs_hit += bool(found)

        for f in found:
            if len(samples) < limit:
                samples.append({"file": str(file), "line": f["line"], "text": f["context"]})

    return {"documents": docs, "words": words, "hits": total, "docs_hit": docs_hit,
            "rate": total * 1000 / words if words else 0.0, "samples": samples}  # fmt: skip


def measure_rule(definition: dict[str, Any], good_path: str, bad_path: str) -> dict[str, Any]:
    """Measure an unsaved rule against both corpora. The gate every proposal passes through."""
    good_size, bad_size = measure_size(Path(good_path)), measure_size(Path(bad_path))
    require_floor(good_size)
    require_floor(bad_size)
    rule, config = build_rule(definition)
    good, bad = _scan(rule, config, Path(good_path)), _scan(rule, config, Path(bad_path))
    ratio = bad["rate"] / good["rate"] if good["rate"] else None
    passes = bad["rate"] > 0 and (ratio is None or ratio >= RATIO_FLOOR)
    MEASURED[fingerprint(definition)] = Measurement(rule.id, ratio, bad["rate"], passes)
    provisional = "provisional" in {good_size.reliability, bad_size.reliability}

    return {
        "rule": rule.id,
        "good_rate_per_1k": round(good["rate"], 3),
        "bad_rate_per_1k": round(bad["rate"], 3),
        "ratio": None if ratio is None else round(ratio, 2),
        "ratio_is_infinite": ratio is None and bad["rate"] > 0,
        "ratio_floor": RATIO_FLOOR,
        "verdict": "keep" if passes else "discard",
        "reason": "" if passes else _discard_reason(ratio, bad["rate"]),
        "provisional": provisional,
        "docs_hit": {"good": f"{good['docs_hit']}/{good['documents']}",
                     "bad": f"{bad['docs_hit']}/{bad['documents']}"},
        "samples": {"good": good["samples"], "bad": bad["samples"]},
    }  # fmt: skip


def _discard_reason(ratio: float | None, bad_rate: float) -> str:
    if bad_rate == 0:
        return "the rule never fires on the bad corpus"

    return f"ratio {ratio:.2f} is under the {RATIO_FLOOR:g} floor: it fires on both corpora"


def find_matches(
    rule_id: str | None, rule_definition: dict[str, Any] | None, path: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Real sentences a rule matches, with file and line."""
    rule, config = _rule_for(rule_id, rule_definition)
    out: list[dict[str, Any]] = []

    for file, text in documents(Path(path)):
        for f in hits(rule, text, config):
            out.append({"file": str(file), "line": f["line"], "col": f["col"],
                        "match": f["span"]["text"], "sentence": f["context"]})  # fmt: skip

            if len(out) >= limit:
                return out

    return out


# ---- suggest_rules ------------------------------------------------------------------------


def _ngrams(text: str, sizes: range) -> list[tuple[str, ...]]:
    tokens = TOKEN.findall(text.lower())

    return [tuple(tokens[i : i + n]) for n in sizes for i in range(len(tokens) - n + 1)]


def _count(root: Path, sizes: range) -> tuple[Counter[tuple[str, ...]], Counter[tuple[str, ...]]]:
    total: Counter[tuple[str, ...]] = Counter()
    docs: Counter[tuple[str, ...]] = Counter()

    for _, text in documents(root):
        grams = _ngrams(text, sizes)
        total.update(grams)
        docs.update(set(grams))

    return total, docs


def _worth_listing(gram: tuple[str, ...]) -> bool:
    return gram[0] not in STOP_WORDS and gram[-1] not in STOP_WORDS


def _context(root: Path, gram: tuple[str, ...], seen: int) -> list[dict[str, Any]]:
    pattern = re.compile(r"\b" + r"\W+".join(re.escape(w) for w in gram) + r"\b", re.IGNORECASE)
    out: list[dict[str, Any]] = []

    for file, text in documents(root):
        for m in pattern.finditer(text):
            lo, hi = max(0, m.start() - SAMPLE_WIDTH), min(len(text), m.end() + SAMPLE_WIDTH)
            line = text.count("\n", 0, m.start()) + 1
            out.append({"file": str(file), "line": line, "text": " ".join(text[lo:hi].split())})

            if len(out) >= seen:
                return out

    return out


def suggest_rules(
    good_path: str, bad_path: str, n_range: tuple[int, int] = (1, 3), min_occurrences: int = 5
) -> dict[str, Any]:
    """N-grams ranked by smoothed log-odds of appearing in the bad corpus over the good one."""
    good_root, bad_root = Path(good_path), Path(bad_path)
    good_size, bad_size = measure_size(good_root), measure_size(bad_root)
    require_floor(good_size)
    require_floor(bad_size)
    sizes = range(n_range[0], n_range[1] + 1)
    good, good_docs = _count(good_root, sizes)
    bad, bad_docs = _count(bad_root, sizes)
    n_good, n_bad = sum(good.values()) or 1, sum(bad.values()) or 1
    vocab = len(set(good) | set(bad))
    alpha = 0.5
    rows = []

    for gram, count in bad.items():
        if count < min_occurrences or not _worth_listing(gram):
            continue

        g = good.get(gram, 0)
        log_odds = math.log((count + alpha) / (n_bad + alpha * vocab)) - math.log(
            (g + alpha) / (n_good + alpha * vocab)
        )
        bad_rate = count * 1000 / bad_size.words
        good_rate = g * 1000 / good_size.words
        rows.append((log_odds, gram, bad_rate, good_rate, g, count))

    rows.sort(reverse=True)
    top = []

    for log_odds, gram, bad_rate, good_rate, g, _ in rows[:SUGGEST_LIMIT]:
        top.append({
            "ngram": " ".join(gram),
            "log_odds": round(log_odds, 3),
            "good_rate_per_1k": round(good_rate, 3),
            "bad_rate_per_1k": round(bad_rate, 3),
            "ratio": None if g == 0 else round(bad_rate / good_rate, 2),
            "docs": {"good": good_docs.get(gram, 0), "bad": bad_docs.get(gram, 0)},
            "samples": {"good": _context(good_root, gram, 2), "bad": _context(bad_root, gram, 2)},
        })  # fmt: skip

    return {
        "good": _size_block(good_size),
        "bad": _size_block(bad_size),
        "provisional": "provisional" in {good_size.reliability, bad_size.reliability},
        "candidates": top,
        "note": "Candidates are n-grams only. Group them, draft rules, then test_rule each one.",
    }


# ---- metrics, baselines and composites ----------------------------------------------------


def get_metrics(text: str) -> dict[str, Any]:
    """The full prose metrics block for a text."""
    result = analyze(text, config=replace(_resolved().config, prose_metrics={"weight": 0.0}))

    return dict(result["prose_metrics"])


def build_baseline(corpus_path: str, name: str) -> dict[str, Any]:
    made = baseline.build(Path(corpus_path), name, _resolved().config)

    return {k: made[k] for k in ("name", "documents", "words", "path")} | {
        "metrics": len(made["metrics"])
    }


def measure_drift(text: str, baseline_name: str) -> dict[str, Any]:
    result = analyze(text, config=replace(_resolved().config, prose_metrics={"weight": 0.0}))

    return baseline.drift(result["prose_metrics"]["metrics"], baseline.load(baseline_name))


def _ratio_key(ratio: float | None) -> float:
    return math.inf if ratio is None else ratio


def measure_composite(definition: dict[str, Any], good_path: str, bad_path: str) -> dict[str, Any]:
    """Measure a composite and each of its members; it must beat every member to be proposed."""
    if definition.get("backend") != "composite":
        raise ValueError("test_composite needs a definition with backend: composite")

    result = measure_rule(definition, good_path, bad_path)
    rule, config = build_rule(definition)
    members = []

    for rid in sorted(composition.dependencies(rule)):
        member = next((r for r in config.rules if r.id == rid), None)

        if member is None:
            continue

        good, bad = _scan(member, config, Path(good_path)), _scan(member, config, Path(bad_path))
        ratio = bad["rate"] / good["rate"] if good["rate"] else None
        members.append({"rule": rid, "good_rate_per_1k": round(good["rate"], 3),
                        "bad_rate_per_1k": round(bad["rate"], 3),
                        "ratio": None if ratio is None else round(ratio, 2),
                        "ratio_is_infinite": ratio is None and bad["rate"] > 0})  # fmt: skip

    composite_ratio = result["ratio"]
    beaten = [
        m["rule"] for m in members if _ratio_key(composite_ratio) <= _ratio_key(m["ratio"])
        and m["bad_rate_per_1k"] > 0
    ]  # fmt: skip
    beats = not beaten
    result["members"] = members
    result["beats_members"] = beats

    if result["verdict"] == "keep" and not beats:
        result["verdict"] = "discard"
        result["reason"] = f"does not beat its member(s) {beaten}: the components do as well alone"
        bad_rate = result["bad_rate_per_1k"]
        MEASURED[fingerprint(definition)] = Measurement(rule.id, composite_ratio, bad_rate, False)

    return result


def baselines_list() -> list[str]:
    return baseline.names()


def baseline_show(name: str) -> dict[str, Any]:
    return baseline.load(name)


def metrics_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": m.name,
            "scopes": list(m.scopes),
            "returns": m.returns,
            "scalars": list(m.scalars),
            "description": m.doc,
        }  # fmt: skip
        for m in load_registry().values()
    ]


# ---- get_rule, validate_fixtures ----------------------------------------------------------


def get_rule(rule_id: str) -> dict[str, Any]:
    resolved = _resolved()
    rule = next((r for r in resolved.config.rules if r.id == rule_id), None)

    if rule is None:
        raise ValueError(f"unknown rule {rule_id!r}")

    return {"rule": asdict(rule), "sources": explain(resolved, rule_id)}


def _cases(raw: Any, where: str) -> list[Case]:
    if not isinstance(raw, list):
        raise ValueError(f"{where} must be a list")

    return [parse_case(c, where) for c in raw]


def validate_fixtures(rule_id: str, fixtures: dict[str, Any]) -> dict[str, Any]:
    """Per-case pass or fail of a proposed fixture set against the current rule."""
    rule, config = _rule_by_id(rule_id)
    fire = _cases(fixtures.get("should_fire", []), "should_fire")
    none = _cases(fixtures.get("should_not_fire", []), "should_not_fire")
    results = []

    for case in fire:
        reason = check_fire(case, hits(rule, case.text, config))
        results.append({"kind": "should_fire", "text": case.text, "passed": not reason,
                        "reason": reason})  # fmt: skip

    for case in none:
        found = hits(rule, case.text, config)
        results.append(
            {
                "kind": "should_not_fire",
                "text": case.text,
                "passed": not found,
                "reason": f"matched {found[0]['span']['text']!r}" if found else "",
            }
        )

    return {
        "rule": rule_id,
        "cases": results,
        "all_passed": all(r["passed"] for r in results),
        "meets_minimum": len(fire) >= MIN_FIRE and len(none) >= MIN_NO_FIRE,
        "minimum": {"should_fire": MIN_FIRE, "should_not_fire": MIN_NO_FIRE},
    }


# ---- writes -------------------------------------------------------------------------------


def _target_dir(target: str) -> Path:
    if target == "user":
        return user_dir()

    if target != "workdir":
        raise ValueError("target is 'workdir' or 'user'")

    return find_project_dir(Path.cwd()) or Path.cwd() / ".clarity"


def _need_approval(approved: bool) -> None:
    if not approved:
        raise ValueError(
            "Show the user the exact content first, then call again with user_approved true "
            "once they accept it."
        )


def _load_yaml(path: Path, key: str) -> Any:
    if not path.is_file():
        return []

    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(key, [])


def write_rules(
    rules: list[dict[str, Any]], user_approved: bool, target: str = "workdir"
) -> dict[str, Any]:
    """Write measured rules that met the ratio floor; refuse the rest with the reason."""
    _need_approval(user_approved)
    accepted, rejected = [], []

    for definition in rules:
        seen = MEASURED.get(fingerprint(definition))
        rid = definition.get("id", "?") if isinstance(definition, dict) else "?"

        if seen is None:
            rejected.append({"id": rid, "reason": "not measured: call test_rule on this exact "
                             "definition with both corpus paths first"})  # fmt: skip
        elif not seen.passes:
            rejected.append({"id": rid, "reason": _discard_reason(seen.ratio, seen.bad_rate)})
        else:
            accepted.append(definition)

    if not accepted:
        return {"written": [], "path": None, "rejected": rejected}

    path = _target_dir(target) / "rules" / RULES_FILE
    ids = {d["id"] for d in accepted}
    kept = [r for r in _load_yaml(path, "rules") if r.get("id") not in ids]
    # Without fixtures a rule would stop the config loading, so it starts experimental.
    stored = [{**d, "experimental": True} for d in accepted]
    text = yaml.safe_dump({"rules": [*kept, *stored]}, sort_keys=False, allow_unicode=True)
    load_config(text=text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    return {
        "written": sorted(ids),
        "path": str(path),
        "rejected": rejected,
        "note": "Rules start experimental (reported, unscored). write_fixtures clears that.",
    }


def write_fixtures(
    rule_id: str, fixtures: dict[str, Any], user_approved: bool, target: str = "workdir"
) -> dict[str, Any]:
    """Write a fixture set that meets the minimum and passes, then take the rule out of
    experimental."""
    _need_approval(user_approved)
    check = validate_fixtures(rule_id, fixtures)

    if not check["meets_minimum"]:
        raise ValueError(f"a rule needs at least {MIN_FIRE} should_fire and {MIN_NO_FIRE} "
                         "should_not_fire cases")  # fmt: skip

    if not check["all_passed"]:
        failed = [c["text"] for c in check["cases"] if not c["passed"]]
        raise ValueError(f"fixtures fail against the current rule: {failed}")

    folder = _target_dir(target) / "rules"
    path = folder / FIXTURES_FILE
    docs = [d for d in _fixture_docs(path) if d.get("rule") != rule_id]
    entry = {"rule": rule_id, "should_fire": fixtures.get("should_fire", []),
             "should_not_fire": fixtures.get("should_not_fire", [])}  # fmt: skip
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all([*docs, entry], sort_keys=False, allow_unicode=True),
                    encoding="utf-8")  # fmt: skip
    cleared = _clear_experimental(folder / RULES_FILE, rule_id)

    return {"path": str(path), "rule": rule_id, "experimental_cleared": cleared}


def _fixture_docs(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []

    return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]


def _clear_experimental(path: Path, rule_id: str) -> bool:
    rules = _load_yaml(path, "rules")
    changed = False

    for rule in rules:
        if rule.get("id") == rule_id and rule.pop("experimental", None):
            changed = True

    if changed:
        path.write_text(yaml.safe_dump({"rules": rules}, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")  # fmt: skip

    return changed


def accept_finding(finding_id: str) -> dict[str, Any]:
    return {"id": finding_id, "newly_accepted": accept(finding_id)}


# ---- resources ----------------------------------------------------------------------------


def categories() -> list[dict[str, Any]]:
    cats = _resolved().config.categories

    return [asdict(c) for _, c in sorted(cats.items())]


def profiles() -> list[dict[str, str]]:
    found = discover_profiles(_resolved().folders)

    return [{"name": p.name, "path": p.path} for p in found.values()]


FLOORS = {
    "hard": {"documents": corpus.HARD_DOCS, "words": corpus.HARD_WORDS},
    "reliable": {"documents": corpus.RELIABLE_DOCS, "words": corpus.RELIABLE_WORDS},
}
