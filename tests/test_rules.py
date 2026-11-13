import pytest
from fixtures import FIXTURES

from clarity.config import load_config
from clarity.engine import analyze


def rule_ids() -> list[str]:
    return [r.id for r in load_config(None).rules]


def test_every_rule_has_a_fixture_pair():
    assert sorted(rule_ids()) == sorted(FIXTURES)


@pytest.mark.parametrize("rule_id", sorted(FIXTURES))
def test_positive_fixture_fires(rule_id):
    text = FIXTURES[rule_id][0]
    result = analyze(text)
    assert rule_id in {f["rule"] for f in result["findings"]}, result["findings"]


@pytest.mark.parametrize("rule_id", sorted(FIXTURES))
def test_negative_fixture_does_not_fire(rule_id):
    text = FIXTURES[rule_id][1]
    result = analyze(text)
    assert rule_id not in {f["rule"] for f in result["findings"]}, result["findings"]
