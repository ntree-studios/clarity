"""A rule that cannot match anything fails at load, naming the rule and what it needs."""

import pytest
import yaml

from clarity.config import ConfigError, load_config


def cfg(*rules):
    return load_config(text=yaml.safe_dump({"rules": list(rules)}))


@pytest.mark.parametrize(
    ("rule", "needs"),
    [
        ({"id": "x", "category": "hedges"}, "phrases, lower_phrases or pattern"),
        ({"id": "x", "category": "hedges", "backend": "phrase"}, "phrases, lower"),
        ({"id": "x", "category": "hedges", "backend": "dependency"}, "patterns"),
        ({"id": "x", "category": "hedges", "backend": "structural"}, "function"),
        ({"id": "x", "category": "hedges", "backend": "structural", "function": "nope"}, "nope"),
    ],
)
def test_a_rule_missing_what_its_backend_needs_is_rejected_at_load(rule, needs):
    with pytest.raises(ConfigError, match="rule x") as exc:
        cfg(rule)

    assert needs in str(exc.value)


def test_complete_rules_of_each_backend_load():
    pattern = [[{"RIGHT_ID": "v", "RIGHT_ATTRS": {"LEMMA": "embark"}}]]
    config = cfg(
        {"id": "a", "category": "hedges", "phrases": ["x"]},
        {"id": "b", "category": "hedges", "lower_phrases": ["x"]},
        {"id": "c", "category": "hedges", "pattern": [{"LEMMA": "x"}]},
        {"id": "d", "category": "hedges", "backend": "dependency", "patterns": pattern},
        {"id": "e", "category": "hedges", "backend": "structural", "function": "long_sentence"},
    )

    assert {"a", "b", "c", "d", "e"} <= {r.id for r in config.rules}


def test_a_partial_override_of_an_existing_rule_still_loads():
    assert cfg({"id": "intensifier", "max_per_1k": 3})


def test_enabled_false_and_disabled_true_both_remove_a_rule():
    for field in ({"enabled": False}, {"disabled": True}):
        config = cfg({"id": "hedge", **field})

        assert "hedge" not in {r.id for r in config.rules}
