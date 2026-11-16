"""Rules carry a description and a remediation; findings carry the remediation."""

import pytest

from clarity.config import ConfigError, describe_rules, load_config
from clarity.engine import analyze

RULE = """
rules:
  - id: r
    category: hedges
    phrases: [really]
    match: lower
    description: An intensifier that adds no information.
    remediation: Delete it, or give the number it stands for.
"""


def test_findings_carry_the_remediation():
    found = analyze("It is really fine.", config=load_config(text=RULE))["findings"]
    mine = [f for f in found if f["rule"] == "r"]

    assert mine and mine[0]["remediation"] == "Delete it, or give the number it stands for."


def test_listing_shows_description_and_remediation():
    row = next(r for r in describe_rules(load_config(text=RULE)) if r["id"] == "r")

    assert row["description"].startswith("An intensifier")
    assert row["remediation"].startswith("Delete it")


def test_the_old_suggestion_field_is_refused_with_its_new_name():
    with pytest.raises(ConfigError, match="renamed to 'remediation'"):
        load_config(text=RULE.replace("remediation:", "suggestion:"))


def test_every_shipped_rule_has_a_description_and_a_remediation():
    missing = [r.id for r in load_config(None).rules if not (r.description and r.remediation)]

    assert missing == []
