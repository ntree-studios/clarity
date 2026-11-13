import pytest

from clarity.config import ConfigError, load_config
from clarity.engine import analyze


def run(text: str, yaml_text: str) -> list[dict]:
    return analyze(text, config=load_config(text=yaml_text))["findings"]


def test_plain_term_reports_under_watchlist_with_term_as_rule_id():
    found = run("We need more synergy.", "watchlist:\n  - {term: synergy, max_per_1k: 0}")

    assert [(f["rule"], f["category"]) for f in found] == [("synergy", "watchlist")]


def test_term_absent_does_not_fire():
    assert not run("We need more teamwork.", "watchlist:\n  - {term: synergy, max_per_1k: 0}")


def test_phrase_match():
    cfg = 'watchlist:\n  - {term: "load-bearing", max_per_1k: 0, match: phrase}'

    assert run("This is a load-bearing wall.", cfg)
    assert not run("This wall bears the load.", cfg)


def test_allowance_marks_findings_over():
    cfg = "watchlist:\n  - {term: synergy, max_per_1k: 1}"
    text = "Synergy is good. " + "The team shipped the build on time. " * 150 + "Synergy again."
    found = [f for f in run(text, cfg) if f["rule"] == "synergy"]

    assert [f["over_allowance"] for f in found] == [False, True]


CONCRETE = "watchlist:\n  - {term: bedrock, max_per_1k: 0, require_concrete_governor: true}"


def test_concrete_governor_fires_on_abstract_noun():
    assert run("It is the bedrock of democracy.", CONCRETE)


def test_concrete_governor_skips_concrete_noun():
    assert not run("It is the bedrock of the cliff.", CONCRETE)


def test_entry_without_term_is_a_config_error():
    with pytest.raises(ConfigError):
        load_config(text="watchlist:\n  - {max_per_1k: 1}")
