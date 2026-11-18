"""The AI-slop rules from the research report, the marker rules and the three starter profiles."""

from importlib import resources
from pathlib import Path

import pytest

from clarity.animacy import is_animate
from clarity.config import load_config
from clarity.engine import analyze
from clarity.fixtures import load_index
from clarity.harness import run_fixtures
from clarity.nlp import get_nlp
from clarity.resolve import resolve

PROFILES = ("technical", "business", "essay")


def rules_of(text, config=None):
    return {f["rule"] for f in analyze(text, config=config or load_config(None))["findings"]}


@pytest.mark.parametrize(
    ("text", "fires"),
    [("The plan holds.", True), ("The bracket holds the shelf.", False),
     ("The variable holds the count.", False)],
)  # fmt: skip
def test_physical_verb_fires_only_on_the_abstract_subject(text, fires):
    assert ("abstract-physical-verb-catalogued" in rules_of(text)) is fires


@pytest.mark.parametrize(
    ("text", "animate"),
    [("Momentum fades quickly.", False), ("Trust grows slowly.", False),
     ("Value moves to the customer.", False), ("Pia had seen the report.", True)],
)  # fmt: skip
def test_a_bare_common_noun_starting_a_sentence_is_not_a_name(text, animate):
    assert is_animate(get_nlp()(text)[0]) is animate


def test_marker_rules_feed_composites_but_are_never_reported():
    text = (
        "Trust is crucial in education. Teachers play a key role in fostering it, and schools "
        "must ensure that every student feels valued."
    )
    found = rules_of(text)

    assert "generic-paragraph" in found
    assert not found & {"evaluative-word", "number-anchor", "name-anchor"}


def test_a_number_clears_the_unquantified_claim():
    assert "unquantified-claim" in rules_of("The new cache significantly improved load times.")
    assert "unquantified-claim" not in rules_of("The cache cut load times by 40 percent.")


def test_ease_words_are_off_unless_a_profile_switches_them_on(tmp_path):
    assert "ease-words" not in {r.id for r in load_config(None).rules}

    source = resources.files("clarity").joinpath("examples", "profiles", "technical.yml")
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "technical.yml").write_text(source.read_text(encoding="utf-8"))
    res = resolve(tmp_path, profile="technical")

    assert "ease-words" in rules_of("Simply open the file.", res.config)


def test_ease_words_fixtures_pass_when_the_rule_is_on():
    config = load_config(text="rules:\n  - {id: ease-words, enabled: true}\n")
    results = run_fixtures(config, load_index([]), "ease-words", None)

    assert results and all(r.passed for r in results)


def test_the_three_starter_profiles_load_and_comment_every_setting(tmp_path):
    folder = Path(str(resources.files("clarity").joinpath("examples", "profiles")))

    assert sorted(p.stem for p in folder.glob("*.yml")) == sorted(PROFILES)
    (tmp_path / "profiles").mkdir()

    for name in PROFILES:
        text = (folder / f"{name}.yml").read_text(encoding="utf-8")
        (tmp_path / "profiles" / f"{name}.yml").write_text(text)

        assert resolve(tmp_path, profile=name).profile.name == name

        for line in _setting_lines(text):
            assert line in _commented(text), f"{name}.yml: no source comment above {line!r}"


def _setting_lines(text):
    """Lines that set a value: indented keys and list items, not names or descriptions."""
    out = []

    for line in text.splitlines():
        bare = line.strip()

        if line.startswith((" ", "-")) and bare and not bare.startswith("#"):
            out.append(line)

    return out


def _commented(text):
    """Setting lines inside a block that a comment opens (a comment line directly above the
    block's first line)."""
    lines, covered, open_ = text.splitlines(), set(), False

    for i, line in enumerate(lines):
        bare = line.strip()

        if bare.startswith("#"):
            open_ = True
        elif not bare or not line.startswith((" ", "-")):
            open_ = bare.endswith(":") and i > 0 and lines[i - 1].strip().startswith("#")
        elif open_:
            covered.add(line)

    return covered


def test_experimental_findings_are_listed_apart_in_the_text_report():
    from test_cli import run

    _, out, _ = run(["check", "-"], stdin="We utilize the new tool every day.")

    assert "EXPERIMENTAL (reported, unscored)" in out
    assert "stiff-synonym" in out and "1 experimental" in out
