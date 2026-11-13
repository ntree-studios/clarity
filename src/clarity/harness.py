"""clarity test, explain and snapshot: make rule testing cheap enough to run on every edit."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path
from typing import Any, TextIO

import yaml

from clarity import baseline, composition
from clarity.config import Config, Rule
from clarity.corpus import corpus_files
from clarity.engine import analyze
from clarity.fixtures import Case, RuleFixtures
from clarity.resolve import Resolved, find_project_dir

CEILING = 2.0
STRONG, NO_SIGNAL = 3.0, 1.5


@dataclass
class Failure:
    kind: str
    number: int
    text: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass
class RuleResult:
    rule: str
    group: str
    fire: int
    no_fire: int
    failures: list[Failure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def focus(rule: Rule, config: Config) -> Config:
    """The config narrowed to one rule and the rules it reads. Keeps a fixture run fast."""
    by_id = {r.id: r for r in config.rules}
    needed = composition.closure(rule, by_id) - {rule.id}

    return replace(config, rules=[*[r for r in config.rules if r.id in needed], rule])


def hits(rule: Rule, text: str, config: Config) -> list[dict[str, Any]]:
    """Findings of one rule on a text, including composites over the rules they read."""
    found = analyze(text, config=focus(rule, config))["findings"]

    return [f for f in found if f["rule"] == rule.id]


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def check_fire(case: Case, found: list[dict[str, Any]]) -> str:
    if not found:
        return "the rule did not match"

    if case.count is not None and len(found) != case.count:
        return f"expected {case.count} matches, got {len(found)}"

    if case.span is not None and _norm(case.span) not in {_norm(f["span"]["text"]) for f in found}:
        got = ", ".join(repr(f["span"]["text"]) for f in found)
        return f"expected span {case.span!r}, matched {got}"

    return ""


def run_fixtures(
    config: Config, index: dict[str, RuleFixtures], target: str | None, only: set[str] | None
) -> list[RuleResult]:
    rules = {r.id: r for r in config.rules}
    results = []

    for rule_id, fx in index.items():
        if rule_id not in rules or (target and target not in {rule_id, fx.group}):
            continue

        if only is not None and rule_id not in only:
            continue

        res = RuleResult(rule_id, fx.group, len(fx.fire), len(fx.no_fire))

        for n, case in enumerate(fx.fire, start=1):
            reason = check_fire(case, hits(rules[rule_id], case.text, config))

            if reason:
                res.failures.append(Failure("should_fire", n, case.text, [], reason))

        for n, case in enumerate(fx.no_fire, start=1):
            found = hits(rules[rule_id], case.text, config)

            if found:
                matched = [
                    {"text": f["span"]["text"], "line": f["line"], "col": f["col"]} for f in found
                ]
                res.failures.append(Failure("should_not_fire", n, case.text, matched))

        results.append(res)

    return sorted(results, key=lambda r: (r.group, r.rule))


def format_results(results: list[RuleResult]) -> str:
    out = []

    for r in results:
        counts = f"{r.fire} fire · {r.no_fire} no-fire"
        out.append(f"{r.rule:<30}{counts:<26}{'PASS' if r.passed else 'FAIL'}")

    for r in results:
        for f in r.failures:
            out += ["", _failure_text(r.rule, f)]

    failed = sum(1 for r in results if not r.passed)
    out += ["", f"{len(results) - failed} passed · {failed} failed"]

    return "\n".join(out)


def _failure_text(rule: str, f: Failure) -> str:
    if f.kind == "should_not_fire":
        m = f.matches[0]
        return (
            f"  should_not_fire case {f.number} matched:\n"
            f'    "{f.text}"\n'
            f'    matched: "{m["text"]}"  at {m["line"]}:{m["col"]}\n'
            f"    rule:    {rule}\n\n"
            "    The fixture asserts this is acceptable usage. Either the fixture\n"
            "    is wrong or the rule needs a position or context constraint."
        )

    return (
        f"  should_fire case {f.number} failed: {f.reason}\n"
        f'    "{f.text}"\n'
        f"    rule:    {rule}\n\n"
        f'    Run: clarity explain {rule} "..." to see where the match breaks.'
    )


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None

    return out.stdout


def _rules_of(data: Any) -> list[dict[str, Any]]:
    return list(data.get("rules", [])) if isinstance(data, dict) else []


def changed_rules(resolved: Resolved) -> set[str] | None:
    """Rule ids whose definition differs from git HEAD, or None when git cannot say."""
    changed: set[str] = set()
    paths = [Path(f) for f in resolved.files] + [
        Path(str(resources.files("clarity").joinpath("default.yml")))
    ]

    for path in paths:
        root = _git(["rev-parse", "--show-toplevel"], path.parent)

        if root is None:
            return None

        rel = path.resolve().relative_to(Path(root.strip()).resolve())
        old = _git(["show", f"HEAD:{rel}"], path.parent)
        now = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        before = yaml.safe_load(old) if old else {}
        was = {r["id"]: r for r in _rules_of(before)}

        for rule in _rules_of(now):
            if was.get(rule["id"]) != rule:
                changed.add(rule["id"])

    return changed


@dataclass
class Corpus:
    documents: int
    words: int
    hits: Counter[str]
    docs_hit: Counter[str]
    samples: dict[str, list[tuple[str, str]]]


def scan_corpus(path: Path, resolved: Resolved) -> Corpus:
    corpus = Corpus(0, 0, Counter(), Counter(), {})

    for file in corpus_files(path):
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        result = analyze(text, source=str(file), config=resolved.config)
        corpus.documents += 1
        corpus.words += result["words"]

        for rule in {f["rule"] for f in result["findings"]}:
            corpus.docs_hit[rule] += 1

        for f in result["findings"]:
            corpus.hits[f["rule"]] += 1
            seen = corpus.samples.setdefault(f["rule"], [])

            if len(seen) < 3:
                seen.append((file.stem, f["span"]["text"].strip()))

    return corpus


def rate(corpus: Corpus, rule: str) -> float:
    return corpus.hits[rule] * 1000 / corpus.words if corpus.words else 0.0


def format_corpus(corpus: Corpus, ceiling: float) -> tuple[str, list[str]]:
    out = [f"Corpus: {corpus.documents} documents · {corpus.words:,} words", ""]
    out.append(f"{'RULE':<28}{'HITS':>6}{'PER 1K':>9}{'DOCS HIT':>12}   FLAGGED")
    flagged = []
    rows = sorted(corpus.hits, key=lambda r: -rate(corpus, r))

    for rule in rows:
        per_k = rate(corpus, rule)
        mark = "← high" if per_k > ceiling else ""
        docs = f"{corpus.docs_hit[rule]}/{corpus.documents}"
        out.append(f"{rule:<28}{corpus.hits[rule]:>6}{per_k:>9.2f}{docs:>12}   {mark}".rstrip())

        if mark:
            flagged.append(rule)

    if flagged:
        out += [
            "",
            f"Flagged: rate exceeds --corpus-ceiling ({ceiling:g} per 1k).",
            "A rule firing this often on accepted writing is either miscalibrated",
            "or describes a habit rather than an error.",
        ]

        for rule in flagged:
            out += ["", f"Sample hits for {rule}:"]
            out += [f'  {doc}  "{span}"' for doc, span in corpus.samples[rule]]

    return "\n".join(out), flagged


def format_against(good: Corpus, bad: Corpus) -> str:
    out = [f"{'RULE':<28}{'GOOD/1K':>9}{'BAD/1K':>9}{'RATIO':>9}"]
    rules = sorted(set(good.hits) | set(bad.hits), key=lambda r: -(rate(bad, r) - rate(good, r)))

    for rule in rules:
        g, b = rate(good, rule), rate(bad, rule)
        ratio = b / g if g else float("inf")
        label = "strong" if ratio >= STRONG else "no signal" if ratio <= NO_SIGNAL else ""
        shown = "inf" if ratio == float("inf") else f"{ratio:.1f}x"
        tail = f"  ← {label}" if label else ""
        out.append(f"{rule:<28}{g:>9.2f}{b:>9.2f}{shown:>9}{tail}")

    return "\n".join(out)


def snapshot_dir() -> Path:
    project = find_project_dir(Path.cwd())

    return (project if project else Path.cwd()) / ".clarity-snapshots"


def _fingerprint(rule: Rule) -> dict[str, Any]:
    allowance = rule.max_per_1k if rule.count_scope == "document" else rule.max_per_scope

    return {
        "allowance": allowance,
        "count_scope": rule.count_scope,
        "position": rule.position,
        "severity": rule.severity,
        "experimental": rule.experimental,
    }


def _snapshot_findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "rule": f["rule"],
            "category": f["category"],
            "line": f["line"],
            "col": f["col"],
            "text": f["span"]["text"],
        }
        for f in result["findings"]
        if f["over_allowance"] and not f.get("experimental")
    ]


def take_snapshot(path: Path, resolved: Resolved, stdout: TextIO) -> None:
    """Record the findings that cost score as the baseline for a document."""
    text = path.read_text(encoding="utf-8")
    result = analyze(text, source=str(path), config=resolved.config)
    folder = snapshot_dir()
    folder.mkdir(parents=True, exist_ok=True)
    findings = _snapshot_findings(result)
    data: dict[str, Any] = {
        "path": str(path.resolve()),
        "profile": resolved.profile.name if resolved.profile else None,
        "rules": {r.id: _fingerprint(r) for r in resolved.config.rules},
        "findings": findings,
    }
    (folder / f"{path.stem}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    baseline.record(path, result)
    stdout.write(f"snapshot: {path.name}  {len(findings)} findings\n")


def _note(rule: str, old: dict[str, Any], new: dict[str, Any], added: bool) -> str:
    if rule not in old["rules"] and rule in new:
        return "[new rule]"

    if rule not in new:
        return "[rule removed]"

    a, b = old["rules"][rule], new[rule]

    if a == b:
        return "[unexplained]"

    if a["allowance"] != b["allowance"]:
        word = "raised" if (b["allowance"] or 0) > (a["allowance"] or 0) else "lowered"
        return f"[allowance {word} {a['allowance']:g} → {b['allowance']:g}]"

    return "[rule changed]"


def _key(f: dict[str, Any]) -> tuple[Any, ...]:
    return (f["rule"], f["line"], f["col"], f["text"])


def diff_snapshots(resolve_for: Any, stdout: TextIO) -> tuple[int, int]:
    """Compare each stored snapshot with a fresh run. Returns (changed, unexplained)."""
    files = sorted(snapshot_dir().glob("*.json"))
    changed = unexplained = 0

    for snap in files:
        old = json.loads(snap.read_text(encoding="utf-8"))
        path = Path(old["path"])
        resolved = resolve_for(path)
        result = analyze(path.read_text(encoding="utf-8"), source=str(path), config=resolved.config)
        now = {r.id: _fingerprint(r) for r in resolved.config.rules}
        before = {_key(f): f for f in old["findings"]}
        after = {_key(f): f for f in _snapshot_findings(result)}
        added = [after[k] for k in after if k not in before]
        removed = [before[k] for k in before if k not in after]

        if not added and not removed:
            stdout.write(f"{path.name:<16}no change\n")

            continue

        changed += 1
        stdout.write(f"{path.name:<16}{len(added)} new findings, {len(removed)} removed\n")

        for sign, items in (("+", added), ("-", removed)):
            for f in items:
                note = _note(f["rule"], old, now, sign == "+")
                unexplained += note == "[unexplained]"
                where = f"{f['line']}:{f['col']}"
                stdout.write(f"  {sign} {where:<8}{f['category']}/{f['rule']:<28}{note}\n")

    stdout.write(f"\n{len(files)} snapshots · {changed} changed\n")

    return changed, unexplained
