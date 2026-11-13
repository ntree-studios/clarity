"""Rule fixtures: sibling *.test.yml files that prove a rule fires and, more to the point, that
it leaves normal prose alone.

    rule: framing-noun-phrase
    should_fire:
      - "The honest framing is that most advice isn't a rule."
      - {text: "The simple answer is no.", expect: {count: 1, span: "The simple answer"}}
    should_not_fire:
      - "The honest broker in the deal was the escrow agent."

A file may hold several YAML documents, one per rule. The file stem is the group name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from clarity.config import Config, ConfigError

MIN_FIRE = 1
MIN_NO_FIRE = 2


@dataclass
class Case:
    text: str
    count: int | None = None
    span: str | None = None


@dataclass
class RuleFixtures:
    rule: str
    group: str
    source: str
    fire: list[Case] = field(default_factory=list)
    no_fire: list[Case] = field(default_factory=list)


def parse_case(raw: Any, where: str) -> Case:
    if isinstance(raw, str):
        return Case(raw)

    if isinstance(raw, dict) and isinstance(raw.get("text"), str):
        expect = raw.get("expect") or {}
        unknown = set(expect) - {"count", "span"}

        if unknown:
            raise ConfigError(f"{where}: unknown expect keys {sorted(unknown)}")

        return Case(raw["text"], expect.get("count"), expect.get("span"))

    raise ConfigError(f"{where}: a case is a string or {{text, expect}}")


def load_file(path: Path) -> list[RuleFixtures]:
    try:
        docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path}: cannot load fixtures: {exc}") from exc

    found = []

    for i, doc in enumerate(docs, start=1):
        where = f"{path}: document {i}"

        if not isinstance(doc, dict) or "rule" not in doc:
            raise ConfigError(f"{where}: needs a 'rule' key")

        unknown = set(doc) - {"rule", "should_fire", "should_not_fire"}

        if unknown:
            raise ConfigError(f"{where}: rule {doc['rule']}: unknown keys {sorted(unknown)}")

        stem = path.name.removesuffix(".test.yml")
        fire_raw, none_raw = doc.get("should_fire") or [], doc.get("should_not_fire") or []
        fire = [parse_case(c, f"{where}: should_fire") for c in fire_raw]
        none = [parse_case(c, f"{where}: should_not_fire") for c in none_raw]
        found.append(RuleFixtures(doc["rule"], stem, str(path), fire, none))

    return found


def fixture_files(folders: list[Path]) -> list[Path]:
    bundled = Path(str(resources.files("clarity").joinpath("rules")))
    roots = [bundled, *[f / "rules" for f in folders]]

    return [p for root in roots if root.is_dir() for p in sorted(root.glob("*.test.yml"))]


def load_index(folders: list[Path]) -> dict[str, RuleFixtures]:
    """Fixtures by rule id; several files for one rule are combined."""
    index: dict[str, RuleFixtures] = {}

    for path in fixture_files(folders):
        for item in load_file(path):
            if item.rule in index:
                known = index[item.rule]
                known.fire += [c for c in item.fire if c not in known.fire]
                known.no_fire += [c for c in item.no_fire if c not in known.no_fire]
            else:
                index[item.rule] = item

    return index


def enforce(config: Config, index: dict[str, RuleFixtures], sources: dict[str, str]) -> None:
    """Refuse a rule without fixtures unless it is experimental or a generated watchlist rule."""
    for rule in config.rules:
        if rule.experimental or rule.fixtures_exempt:
            continue

        have = index.get(rule.id)
        fire, none = (len(have.fire), len(have.no_fire)) if have else (0, 0)

        if fire < MIN_FIRE or none < MIN_NO_FIRE:
            where = sources.get(rule.id, "config")
            raise ConfigError(
                f"{where}: rule {rule.id}: has {fire} should_fire and {none} should_not_fire "
                f"fixtures; needs at least {MIN_FIRE} and {MIN_NO_FIRE} in a rules/*.test.yml "
                "file, or set experimental: true"
            )
