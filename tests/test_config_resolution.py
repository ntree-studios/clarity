"""Config discovery, per-key merging, profiles and load-time validation."""

import json
from pathlib import Path

import pytest
from test_cli import run

from clarity.cli import main
from clarity.config import ConfigError
from clarity.resolve import resolve


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    home, project = tmp_path / "home", tmp_path / "proj" / "docs"
    (home / "rules").mkdir(parents=True)
    (project / ".clarity" / "rules").mkdir(parents=True)
    (project / "sub").mkdir()
    monkeypatch.setenv("CLARITY_HOME", str(home))
    monkeypatch.chdir(project / "sub")

    return home, project / ".clarity", project / "sub"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def rule(res, rule_id):
    return next(r for r in res.config.rules if r.id == rule_id)


def test_nearest_wins_and_resolution_walks_up_from_the_input(dirs):
    home, project, sub = dirs
    write(home / "clarity.yml", "categories:\n  hedges: {weight: 3.0}\n")
    write(project / "clarity.yml", "categories:\n  hedges: {weight: 5.0}\n")
    res = resolve(None, sub)

    assert res.config.categories[8].weight == 5.0
    tails = [f.split("/")[-2:] for f in res.files]
    assert tails == [["home", "clarity.yml"], [".clarity", "clarity.yml"]]


def test_explicit_config_bypasses_resolution(dirs, tmp_path):
    home, project, sub = dirs
    write(project / "clarity.yml", "categories:\n  hedges: {weight: 5.0}\n")
    only = tmp_path / "only.yml"
    write(only, "categories:\n  hedges: {weight: 9.0}\n")
    res = resolve(only, sub)

    assert res.config.categories[8].weight == 9.0
    assert res.files == [str(only)]


def test_explicit_config_layers_several_files_and_directories_in_order(dirs, tmp_path):
    _, project, sub = dirs
    write(project / "clarity.yml", "categories:\n  hedges: {weight: 5.0}\n")
    first = tmp_path / "first.yml"
    write(first, "categories:\n  hedges: {weight: 7.0}\n")
    pack = tmp_path / "pack"
    write(pack / "rules" / "a.yml", "rules:\n  - {id: corporate-tier-a, max_per_1k: 2}\n")
    write(pack / "rules" / "b.yml", "rules:\n  - {id: em-dash, enabled: false}\n")
    write(pack / "profiles" / "p.yml", "name: p\ndisable: [hedge]\n")
    res = resolve([first, pack], sub, "p")
    ids = {r.id for r in res.config.rules}

    assert res.config.categories[8].weight == 7.0
    assert rule(res, "corporate-tier-a").max_per_1k == 2
    assert "em-dash" not in ids and "hedge" not in ids
    assert [Path(f).name for f in res.files] == ["first.yml", "a.yml", "b.yml"]


def test_missing_explicit_config_is_a_load_error(dirs, tmp_path):
    _, _, sub = dirs

    with pytest.raises(ConfigError, match=r"nope\.yml: config not found"):
        resolve([tmp_path / "nope.yml"], sub)


def test_cli_config_flag_repeats(dirs, tmp_path):
    a, b = tmp_path / "a.yml", tmp_path / "b.yml"
    write(a, "rules:\n  - {id: em-dash, enabled: false}\n")
    write(b, "rules:\n  - {id: hedge, enabled: false}\n")
    code, out, _ = run(["config", "--validate", "--config", str(a), "--config", str(b)])

    assert code == 0 and out.startswith("ok:") and "2 files" in out


def test_rules_merge_field_by_field_and_lists_edit_with_plus_and_minus(dirs):
    _, project, sub = dirs
    write(
        project / "rules" / "corp.yml",
        "rules:\n  - id: corporate-tier-a\n    max_per_1k: 0.5\n"
        "    phrases+: [synergize]\n    phrases-: [robust]\n",
    )
    r = rule(resolve(None, sub), "corporate-tier-a")

    assert r.max_per_1k == 0.5 and r.severity == "warning"
    assert "synergize" in r.phrases and "robust" not in r.phrases and "leverage" in r.phrases


def test_removing_an_item_not_inherited_names_file_rule_and_item(dirs):
    _, project, sub = dirs
    write(project / "rules" / "bad.yml", "rules:\n  - id: corporate-tier-a\n    phrases-: [nope]\n")

    with pytest.raises(ConfigError, match=r"bad\.yml.*corporate-tier-a.*nope"):
        resolve(None, sub)


def test_enabled_false_turns_off_an_inherited_rule(dirs):
    _, project, sub = dirs
    write(project / "rules" / "off.yml", "rules:\n  - {id: em-dash, enabled: false}\n")

    assert "em-dash" not in {r.id for r in resolve(None, sub).config.rules}


PROFILE = """name: p
disable: [long-sentence]
rule_override:
  - {id: subject-verb-distance, max_tokens: 12}
allowance_multiplier: {corporate-vocabulary: 0.5}
weight_override: {readability: 0.0}
"""


def test_profile_applies_disable_override_multiplier_and_weight(dirs):
    _, project, sub = dirs
    write(project / "profiles" / "p.yml", PROFILE)
    write(project / "clarity.yml", "profile: p\n")
    res = resolve(None, sub)

    assert res.profile.name == "p"
    assert "long-sentence" not in {r.id for r in res.config.rules}
    assert rule(res, "subject-verb-distance").params["max_tokens"] == 12
    assert rule(res, "corporate-tier-a").max_per_1k == 0.5
    assert res.config.readability["weight"] == 0.0


def test_multipliers_apply_to_the_already_overridden_value_and_stay_fractional(dirs):
    _, project, sub = dirs
    write(project / "rules" / "o.yml", "rules:\n  - {id: corporate-tier-a, max_per_1k: 3}\n")
    quarter = "name: p\nallowance_multiplier: {corporate-vocabulary: 0.25}\n"
    write(project / "profiles" / "p.yml", quarter)
    write(project / "clarity.yml", "profile: p\n")

    assert rule(resolve(None, sub), "corporate-tier-a").max_per_1k == 0.75


def test_profile_flag_beats_the_config_key_and_none_disables(dirs):
    _, project, sub = dirs
    write(project / "profiles" / "p.yml", "name: p\ndisable: [em-dash]\n")
    write(project / "clarity.yml", "profile: p\n")

    write(project / "profiles" / "q.yml", "name: q\ndisable: [hedge]\n")

    assert resolve(None, sub, "none").profile is None
    assert resolve(None, sub, "q").profile.name == "q"


def test_unknown_profile_is_a_load_error_listing_what_exists(dirs):
    home, project, sub = dirs
    write(home / "profiles" / "mine.yml", "name: mine\n")
    write(project / "profiles" / "theirs.yml", "name: theirs\n")

    with pytest.raises(ConfigError, match=r"unknown profile 'nope'.*mine.*theirs"):
        resolve(None, sub, "nope")


def test_shipped_profiles_work_without_init(dirs):
    _, _, sub = dirs

    for name in ("technical", "business", "essay"):
        res = resolve(None, sub, name)
        assert res.profile.name == name
        assert res.profile.path.endswith(f"examples/profiles/{name}.yml")


def test_a_user_profile_replaces_the_shipped_one_of_the_same_name(dirs):
    _, project, sub = dirs
    write(project / "profiles" / "technical.yml", "name: technical\ndisable: [hedge]\n")
    res = resolve(None, sub, "technical")

    assert res.profile.path.endswith(".clarity/profiles/technical.yml")
    assert "hedge" not in {r.id for r in res.config.rules}


def test_builtin_false_drops_shipped_rules_and_profiles_but_keeps_settings(dirs):
    _, project, sub = dirs
    own = "builtin: false\nwatchlist:\n  - {term: synergy, max_per_1k: 0}\n"
    write(project / "clarity.yml", own)
    res = resolve(None, sub)

    assert [r.id for r in res.config.rules] == ["synergy"]
    assert res.profiles == {} and res.builtin is False
    assert res.config.categories

    with pytest.raises(ConfigError, match=r"unknown profile 'technical'.*none defined"):
        resolve(None, sub, "technical")


def test_builtin_must_be_a_boolean(dirs):
    _, project, sub = dirs
    write(project / "clarity.yml", "builtin: no-thanks\n")

    with pytest.raises(ConfigError, match="builtin must be true or false"):
        resolve(None, sub)


def test_environment_supplies_config_and_profile_when_no_flag_does(dirs, tmp_path, monkeypatch):
    _, project, sub = dirs
    write(project / "clarity.yml", "categories:\n  hedges: {weight: 5.0}\n")
    env_cfg = tmp_path / "env.yml"
    write(env_cfg, "categories:\n  hedges: {weight: 6.0}\n")
    monkeypatch.setenv("CLARITY_CONFIG", str(env_cfg))
    monkeypatch.setenv("CLARITY_PROFILE", "essay")
    res = resolve(None, sub)

    assert res.config.categories[8].weight == 6.0
    assert res.profile.name == "essay"
    assert resolve(None, sub, "none").profile is None


def test_rule_without_fixtures_is_refused_unless_experimental(dirs):
    _, project, sub = dirs
    plain = "rules:\n  - {id: my-rule, category: hedges, phrases: [zork]}\n"
    write(project / "rules" / "new.yml", plain)

    with pytest.raises(ConfigError, match=r"new\.yml.*my-rule.*should_not_fire"):
        resolve(None, sub)

    experimental = plain.replace("[zork]}", "[zork], experimental: true}")
    write(project / "rules" / "new.yml", experimental)

    assert rule(resolve(None, sub), "my-rule").experimental is True


def test_experimental_rules_report_findings_but_are_not_scored(dirs, monkeypatch):
    _, project, sub = dirs
    text = "We saw the zork on Monday."
    write(
        project / "rules" / "new.yml",
        "rules:\n  - {id: my-rule, category: hedges, phrases: [zork], experimental: true}\n",
    )
    _, out, _ = run(["check", "-", "--format", "json", "--fail-under", "0"], stdin=text)
    data = json.loads(out)

    assert any(f["rule"] == "my-rule" and f.get("experimental") for f in data["findings"])
    assert data["score"] == 100
    assert next(c for c in data["categories"] if c["id"] == "hedges")["found"] == 0


def test_output_names_the_configs_and_profile_loaded(dirs):
    _, project, sub = dirs
    write(project / "profiles" / "essay.yml", "name: essay\n")
    write(project / "clarity.yml", "profile: essay\n")
    _, out, _ = run(["check", "-", "--fail-under", "0"], stdin="Plain text here.")
    data = json.loads(run(["check", "-", "--format", "json"], stdin="Plain text here.")[1])

    assert "config: bundled" in out and "profile: essay" in out
    assert data["config_sources"][0].endswith("clarity.yml")
    assert data["profile"]["name"] == "essay"


def test_config_command_validates_and_explains(dirs):
    _, project, _ = dirs
    write(project / "rules" / "c.yml", "rules:\n  - {id: corporate-tier-a, max_per_1k: 0.5}\n")
    code, out, _ = run(["config", "--validate"])
    _, explained, _ = run(["config", "--explain", "corporate-tier-a"])

    assert code == 0 and out.startswith("ok:")
    assert "c.yml" in explained and "effective" in explained


def test_init_populates_the_user_directory_without_overwriting(dirs):
    home, _, _ = dirs
    run(["init"])
    (home / "clarity.yml").write_text("# mine\n")
    _, out, _ = run(["init"])

    assert (home / "profiles" / "technical.yml").exists()
    assert not (home / "rules" / "default.yml").exists()
    assert (home / "rules" / "hedges.yml").exists()
    assert (home / "rules" / "hedges.test.yml").exists()
    assert (home / "clarity.yml").read_text() == "# mine\n"
    assert "already present" in out
    assert main is not None


def test_example_rules_are_off_by_default_and_work_when_copied_into_a_config_folder(dirs):
    from importlib import resources

    _, project, _ = dirs
    ids = {"sentence-restatement", "redundant-closer"}

    assert not ids & {r.id for r in resolve(None, project).config.rules}

    for example in resources.files("clarity").joinpath("examples").iterdir():
        if not example.is_file():
            continue

        write(project / "rules" / example.name, example.read_text(encoding="utf-8"))

    assert ids <= {r.id for r in resolve(None, project).config.rules}

    code, out, _ = run(["test"])

    assert code == 0
    assert "redundant-closer" in out and "0 failed" in out


def test_init_split_keeps_every_bundled_rule_once():
    from importlib import resources

    import yaml

    from clarity.config_cmds import split_rules_by_category

    text = resources.files("clarity").joinpath("default.yml").read_text(encoding="utf-8")
    bundled = [r["id"] for r in yaml.safe_load(text)["rules"]]
    _, _, rules = text.partition("\nrules:\n")
    split = split_rules_by_category(rules)
    found = []

    for category, body in split.items():
        parsed = yaml.safe_load("rules:\n" + body)["rules"]
        assert {r["category"] for r in parsed} == {category}
        found += [r["id"] for r in parsed]

    assert sorted(found) == sorted(bundled)
