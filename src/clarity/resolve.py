"""Config discovery, layered merge, profiles and merge explanations.

Two locations, nearest wins: the user directory ($CLARITY_HOME or ~/.clarity) and the first
.clarity/ found walking up from the input. The bundled pack is the base under both.
"""

from __future__ import annotations

import os
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
    record,
)

DIR_NAME = ".clarity"
ENV_HOME = "CLARITY_HOME"
PROFILE_KEYS = {
    "name", "description", "allowance_multiplier", "weight_override", "disable",
    "rule_override", "readability",
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
        data = read_yaml(path) or {}
        unknown = set(data) - PROFILE_KEYS

        if unknown:
            raise ConfigError(f"{path}: unknown profile keys {sorted(unknown)}")

        name = data.get("name", path.stem)
        found[name] = Profile(name, data, str(path))

    return found


def discover_profiles(folders: list[Path]) -> dict[str, Profile]:
    """Bundled examples first, then each directory in order; the nearest name wins."""
    bundled = Path(str(resources.files("clarity").joinpath("profiles")))
    found = _profiles_in(bundled) if bundled.is_dir() else {}

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
    """disable, then rule_override, then allowance_multiplier, then weight_override."""
    data, path = profile.data, profile.path

    for rid in data.get("disable") or []:
        _known_rule(merged, rid, path, "disable")["disabled"] = True
        record(prov, f"rule:{rid}", "enabled", path, False, "profile disable")

    for item in data.get("rule_override") or []:
        target = _known_rule(merged, item.get("id"), path, "rule_override")
        fields = {k: v for k, v in item.items() if k != "id"}
        known = {k: v for k, v in fields.items() if k in RULE_FIELDS}
        merge_fields(target, known, path, prov, f"rule:{item['id']}")

        for key, value in fields.items():
            if key not in RULE_FIELDS:
                target["params"] = {**target.get("params", {}), key: value}
                record(prov, f"rule:{item['id']}", key, path, value, "profile rule_override")

    _multiply_allowances(merged, prov, data.get("allowance_multiplier") or {}, path)

    for name, weight in (data.get("weight_override") or {}).items():
        _override_weight(merged, prov, name, weight, path)

    merge_fields(merged["readability"], data.get("readability") or {}, path, prov, "readability")


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


def resolve(
    explicit: str | Path | None = None,
    start: Path | None = None,
    profile: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Resolved:
    """Resolve the config for an input at start (default: the working directory).

    extra is one more layer applied last, for a rule that is being tested but not yet saved.
    """
    layers = [Layer("bundled", _read_default())]
    folders: list[Path] = []

    if explicit is not None:
        path = Path(explicit)
        layers.append(_as_layer(path, None))
        folders = [path.resolve().parent]
    else:
        user, project = user_dir(), find_project_dir(start or Path.cwd())

        for folder in (user, project):
            if folder is not None and folder.is_dir() and folder not in folders:
                folders.append(folder)
                layers.extend(dir_layers(folder))

    if extra is not None:
        layers.append(Layer("<proposed>", extra))

    merged, prov = merge_layers(layers)
    chosen = _select_profile(profile, merged, discover_profiles(folders))

    if chosen is not None:
        apply_profile(merged, prov, chosen)

    files = [layer.source for layer in layers if layer.source != "bundled"]
    config = build_config(merged, prov)
    sources = {r.id: _rule_source(prov, r.id) for r in config.rules}
    fixtures.enforce(config, fixtures.load_index(folders), sources)

    return Resolved(config, files, chosen, prov, merged, folders)


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
