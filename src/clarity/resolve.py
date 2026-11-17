"""Config discovery, layered merge, profiles and merge explanations.

Two locations, nearest wins: the user directory ($CLARITY_HOME or ~/.clarity) and the first
.clarity/ found walking up from the input. $CLARITY_CONFIG (paths joined with the OS path
separator) replaces discovery when no --config is given, and $CLARITY_PROFILE picks a profile when
no --profile is given; the MCP server sets both from its own flags.

The shipped rule pack and the shipped profiles are the base under every layer. `builtin: false`
in any layer drops the shipped rules, watchlist and profiles and keeps the engine settings
(categories, scoring, readability, topics), so a user can run only their own rules.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from clarity import fixtures
from clarity.config import (
    Config,
    ConfigError,
    Layer,
    Provenance,
    Rule,
    _read_default,
    build_config,
    merge_fields,
    merge_layers,
    merge_rules,
    merge_topics,
    record,
)

DIR_NAME = ".clarity"
ENV_HOME = "CLARITY_HOME"
ENV_CONFIG = "CLARITY_CONFIG"
ENV_PROFILE = "CLARITY_PROFILE"
SHIPPED_ONLY = ("rules", "watchlist")
PROFILE_KEYS = {
    "name", "description", "allowance_multiplier", "weight_override", "disable",
    "rule_override", "readability", "topics", "rules",
}  # fmt: skip
RULE_FIELDS = set(Rule.__dataclass_fields__)


@dataclass
class Profile:
    name: str
    data: dict[str, Any]
    path: str


@dataclass
class Resolved:
    config: Config
    files: list[str] = field(default_factory=list)
    profile: Profile | None = None
    provenance: Provenance = field(default_factory=dict)
    merged: dict[str, Any] = field(default_factory=dict)
    folders: list[Path] = field(default_factory=list)
    profiles: dict[str, Profile] = field(default_factory=dict)
    builtin: bool = True


def user_dir() -> Path:
    return Path(os.environ.get(ENV_HOME) or Path.home() / DIR_NAME)


def find_project_dir(start: Path) -> Path | None:
    """The first .clarity directory walking up from start to the filesystem root."""
    for folder in [start.resolve(), *start.resolve().parents]:
        if (folder / DIR_NAME).is_dir():
            return folder / DIR_NAME

    return None


def read_yaml(path: Path) -> Any:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

    return data


def _as_layer(path: Path, key: str | None) -> Layer:
    data = read_yaml(path) or {}

    if isinstance(data, list) and key:
        data = {key: data}

    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    return Layer(str(path), data)


def dir_layers(folder: Path) -> list[Layer]:
    """clarity.yml, then rules/*.yml alphabetically, then watchlist.yml."""
    layers = []

    if (folder / "clarity.yml").is_file():
        layers.append(_as_layer(folder / "clarity.yml", None))

    for rule_file in sorted((folder / "rules").glob("*.yml")):
        if not rule_file.name.endswith(".test.yml"):
            layers.append(_as_layer(rule_file, "rules"))

    if (folder / "watchlist.yml").is_file():
        layers.append(_as_layer(folder / "watchlist.yml", "watchlist"))

    return layers


def _profiles_in(folder: Path) -> dict[str, Profile]:
    found = {}

    for path in sorted(folder.glob("*.yml")):
        if path.name.endswith(".test.yml"):
            continue

        data = read_yaml(path) or {}
        unknown = set(data) - PROFILE_KEYS

        if unknown:
            raise ConfigError(f"{path}: unknown profile keys {sorted(unknown)}")

        name = data.get("name", path.stem)
        found[name] = Profile(name, data, str(path))

    return found


def shipped_profiles_dir() -> Path:
    return Path(str(resources.files("clarity").joinpath("examples", "profiles")))


def discover_profiles(folders: list[Path], builtin: bool = True) -> dict[str, Profile]:
    """The shipped profiles (unless builtin is off), then each config directory's in order; the
    nearest name wins, so a user profile named like a shipped one replaces it."""
    found: dict[str, Profile] = _profiles_in(shipped_profiles_dir()) if builtin else {}

    for folder in folders:
        if (folder / "profiles").is_dir():
            found.update(_profiles_in(folder / "profiles"))

    return found


def _category_id(raw: Any, merged: dict[str, Any]) -> str | None:
    if isinstance(raw, str):
        return raw

    found = merged["categories"].get(raw, {}).get("id")

    return found if isinstance(found, str) else None


def _known_rule(merged: dict[str, Any], rid: Any, path: str, what: str) -> dict[str, Any]:
    if rid not in merged["rules"]:
        raise ConfigError(f"{path}: {what} refers to unknown rule {rid!r}")

    return merged["rules"][rid]  # type: ignore[no-any-return]


def apply_profile(merged: dict[str, Any], prov: Provenance, profile: Profile) -> None:
    """rules, then disable, then rule_override, then allowance_multiplier, then weight_override,
    then readability and topics settings. Rules a profile adds exist only while it is active."""
    data, path = profile.data, profile.path
    merge_rules(merged, data.get("rules") or [], path, prov)

    for rid in data.get("disable") or []:
        _known_rule(merged, rid, path, "disable")["disabled"] = True
        record(prov, f"rule:{rid}", "enabled", path, False, "profile disable")

    override_rules(merged, prov, data.get("rule_override") or [], path)
    _multiply_allowances(merged, prov, data.get("allowance_multiplier") or {}, path)

    for name, weight in (data.get("weight_override") or {}).items():
        _override_weight(merged, prov, name, weight, path)

    merge_fields(merged["readability"], data.get("readability") or {}, path, prov, "readability")
    merge_topics(merged["topics"], data.get("topics"), path, prov)


def override_rules(
    merged: dict[str, Any], prov: Provenance, items: list[dict[str, Any]], path: str
) -> None:
    """rule_override items: {id, field: value}. Rule fields merge, enabled switches the rule on
    or off, and any other key becomes a param."""
    for item in items:
        target = _known_rule(merged, item.get("id"), path, "rule_override")
        fields = {k: v for k, v in item.items() if k != "id"}
        # enabled: true switches on a rule the pack ships off (ease-words in technical).
        known = {k: v for k, v in fields.items() if k in RULE_FIELDS or k == "enabled"}
        merge_fields(target, known, path, prov, f"rule:{item['id']}")

        for key, value in fields.items():
            if key not in known:
                target["params"] = {**target.get("params", {}), key: value}
                record(prov, f"rule:{item['id']}", key, path, value, "profile rule_override")


SWITCHES = "<disable/enable>"


def switches(
    disable: Sequence[str] | None = None, enable: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    """disable and enable arguments as rule_override items, disables first so an enable can
    turn one rule back on inside a disabled category. Each value may hold several ids split by
    commas. The ids may be rule ids or category ids; resolve() expands and checks them."""

    def ids(values: Sequence[str] | None) -> list[str]:
        return [i.strip() for v in values or [] for i in v.split(",") if i.strip()]

    return [{"id": i, "enabled": False} for i in ids(disable)] + [
        {"id": i, "enabled": True} for i in ids(enable)
    ]


def _split_prefix(raw: str) -> tuple[str | None, str]:
    """("rule", "x") for "rule:x", ("category", "x") for "category:x", (None, raw) otherwise."""
    kind, sep, name = raw.partition(":")

    return (kind, name) if sep and kind in ("rule", "category") else (None, raw)


def _expand_switches(merged: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A category id becomes one item per rule in that category. A bare name that is both a
    category and a rule means the category. "rule:name" or "category:name" picks one. Unknown
    ids are an error that lists them all. A composite rule goes off with any member that is
    switched off, since it cannot run without it."""
    categories = {c.get("id") for c in merged["categories"].values()}
    named = [(_split_prefix(i["id"]), i) for i in items]
    unknown = sorted({
        i["id"] for (kind, name), i in named
        if not (kind != "rule" and name in categories
                or kind != "category" and name in merged["rules"])
    })  # fmt: skip

    if unknown:
        raise ConfigError(f"unknown rule or category ids: {', '.join(unknown)}")

    out = []

    for (kind, name), item in named:
        is_category = name in categories if kind is None else kind == "category"

        if not is_category:
            out.append({**item, "id": name})

            continue

        out.extend({**item, "id": rid} for rid, rule in merged["rules"].items()
                   if _category_id(rule.get("category"), merged) == name)  # fmt: skip

    disables = [i for i in out if not i["enabled"]]
    enables = [i for i in out if i["enabled"]]
    dependents = _dependents(merged, {i["id"] for i in disables} - {i["id"] for i in enables})

    return disables + [{"id": rid, "enabled": False} for rid in dependents] + enables


def _dependents(merged: dict[str, Any], off: set[str]) -> list[str]:
    """Composite rules that name a rule in off as a member, directly or through another
    composite."""
    from clarity.composition import GROUPS

    found: list[str] = []
    changed = True

    while changed:
        changed = False

        for rid, rule in merged["rules"].items():
            members = {m.get("rule") for g in GROUPS for m in rule.get(g) or []
                       if isinstance(m, dict)}  # fmt: skip

            if rid not in off and members & off:
                off.add(rid)
                found.append(rid)
                changed = True

    return found


def _multiply_allowances(
    merged: dict[str, Any], prov: Provenance, multipliers: dict[str, float], path: str
) -> None:
    known = {c["id"] for c in merged["categories"].values()}

    for category, factor in multipliers.items():
        if category not in known:
            raise ConfigError(
                f"{path}: allowance_multiplier refers to unknown category {category!r}"
            )

        for rid, rule in merged["rules"].items():
            if _category_id(rule.get("category"), merged) != category:
                continue

            for fld in ("max_per_1k", "max_per_scope"):
                if rule.get(fld) is not None:
                    rule[fld] = rule[fld] * factor
                    note = f"profile multiplier {factor:g}, active"
                    record(prov, f"rule:{rid}", fld, path, rule[fld], note)


def _override_weight(
    merged: dict[str, Any], prov: Provenance, name: str, weight: float, path: str
) -> None:
    if name in ("readability", "prose_metrics"):
        merged[name]["weight"] = weight
        record(prov, name, "weight", path, weight, "profile weight_override")

        return

    for cat in merged["categories"].values():
        if cat["id"] == name:
            cat["weight"] = weight
            record(prov, f"category:{name}", "weight", path, weight, "profile weight_override")

            return

    raise ConfigError(f"{path}: weight_override refers to unknown category {name!r}")


def _explicit_paths(explicit: str | Path | Sequence[str | Path]) -> list[Path]:
    """--config values: files, or config directories laid out like .clarity/, in order."""
    items = [explicit] if isinstance(explicit, (str, Path)) else list(explicit)
    paths = [Path(item) for item in items]

    for path in paths:
        if not path.exists():
            raise ConfigError(f"{path}: config not found")

    return paths


def resolve(
    explicit: str | Path | Sequence[str | Path] | None = None,
    start: Path | None = None,
    profile: str | None = None,
    extra: dict[str, Any] | None = None,
    overrides: list[dict[str, Any]] | None = None,
) -> Resolved:
    """Resolve the config for an input at start (default: the working directory).

    explicit replaces discovery with one or more --config paths, applied in order. A file is
    one layer; a directory loads like a .clarity/ folder (clarity.yml, rules/*.yml,
    watchlist.yml, profiles/).

    extra is one more layer applied last, for a rule that is being tested but not yet saved.
    overrides are rule_override items from switches(), applied after the profile so a disable or
    enable argument beats both the config files and the profile.
    """
    layers: list[Layer] = []
    folders: list[Path] = []
    env = os.environ.get(ENV_CONFIG)

    if explicit is None and env:
        explicit = [p for p in env.split(os.pathsep) if p]

    if profile is None:
        profile = os.environ.get(ENV_PROFILE) or None

    if explicit is not None:
        for path in _explicit_paths(explicit):
            if path.is_dir():
                layers.extend(dir_layers(path))
                folder = path.resolve()
            else:
                layers.append(_as_layer(path, None))
                folder = path.resolve().parent

            if folder not in folders:
                folders.append(folder)
    else:
        user, project = user_dir(), find_project_dir(start or Path.cwd())

        for candidate in (user, project):
            if candidate is not None and candidate.is_dir() and candidate not in folders:
                folders.append(candidate)
                layers.extend(dir_layers(candidate))

    if extra is not None:
        layers.append(Layer("<proposed>", extra))

    builtin = _builtin(layers)
    shipped = _read_default()

    if not builtin:
        shipped = {k: v for k, v in shipped.items() if k not in SHIPPED_ONLY}

    layers.insert(0, Layer("bundled", shipped))
    merged, prov = merge_layers(layers)
    available = discover_profiles(folders, builtin)
    chosen = _select_profile(profile, merged, available)

    if chosen is not None:
        apply_profile(merged, prov, chosen)

    if overrides:
        override_rules(merged, prov, _expand_switches(merged, overrides), SWITCHES)

    files = [layer.source for layer in layers if layer.source != "bundled"]
    config = build_config(merged, prov)
    sources = {r.id: _rule_source(prov, r.id) for r in config.rules}
    fixtures.enforce(config, fixtures.load_index(folders, profile_fixtures(chosen)), sources)

    return Resolved(config, files, chosen, prov, merged, folders, available, builtin)


def _builtin(layers: list[Layer]) -> bool:
    """The nearest layer's builtin: value; true when no layer sets it."""
    value = True

    for layer in layers:
        if "builtin" in layer.data:
            value = layer.data["builtin"]

            if not isinstance(value, bool):
                raise ConfigError(f"{layer.source}: builtin must be true or false")

    return value


def profile_fixtures(profile: Profile | None) -> list[Path]:
    """profiles/<name>.test.yml beside the active profile: fixtures for the rules it adds."""
    if profile is None:
        return []

    path = Path(profile.path)
    sibling = path.with_name(path.name.removesuffix(".yml") + ".test.yml")

    return [sibling] if sibling.is_file() else []


def _rule_source(prov: Provenance, rule_id: str) -> str:
    events = [e[0] for ev in prov.get(f"rule:{rule_id}", {}).values() for e in ev]

    return events[-1] if events else "config"


def _select_profile(
    arg: str | None, merged: dict[str, Any], available: dict[str, Profile]
) -> Profile | None:
    """--profile name or none, then profile: in the nearest clarity.yml, then no profile."""
    name = arg if arg is not None else merged.get("profile")

    if name in (None, "none"):
        return None

    if name not in available:
        listing = ", ".join(sorted(available)) or "none defined"
        raise ConfigError(f"unknown profile {name!r}; available profiles: {listing}")

    return available[name]


def display(path: str) -> str:
    """~ for the home directory and . for the working directory."""
    home, cwd = str(Path.home()), str(Path.cwd())

    if path.startswith(cwd):
        return "." + path[len(cwd):]

    return "~" + path[len(home):] if path.startswith(home) else path


def config_line(resolved: Resolved) -> str:
    mains = [display(f) for f in resolved.files if f.endswith("clarity.yml")] or [
        display(f) for f in resolved.files[:1]
    ]

    return "config: " + " → ".join(["bundled", *mains])


def profile_line(resolved: Resolved) -> str | None:
    p = resolved.profile

    return f"profile: {p.name} ({display(p.path)})" if p else None


def explain(resolved: Resolved, rule_id: str) -> str:
    """Every field of a rule with the file that set it, in the order it was set."""
    scope = f"rule:{rule_id}"

    if scope not in resolved.provenance:
        raise ConfigError(f"unknown rule {rule_id!r}")

    lines = [rule_id]

    for fld, events in resolved.provenance[scope].items():
        for i, (source, shown, note) in enumerate(events):
            label = fld if i == 0 else ""
            tail = f"  ({note})" if note else ""
            lines.append(f"  {label:<14}{shown[:34]:<36}{display(source)}{tail}")

    rule = next((r for r in resolved.config.rules if r.id == rule_id), None)

    if rule is None:
        lines.append("  effective     disabled")
    else:
        allowance = (
            f"max_per_1k: {rule.max_per_1k:g}"
            if rule.count_scope == "document"
            else f"max_per_scope: {rule.max_per_scope:g}"
        )
        lists = [f"{len(v)} {k}" for k, v in vars(rule).items() if isinstance(v, list) and v]
        lines.append("  effective     " + " · ".join([allowance, *lists]))

    return "\n".join(lines)
