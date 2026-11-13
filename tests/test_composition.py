"""Composites, suppress_if, active_when and allowance_when: load-time validation and behavior."""

import pytest
import yaml
from test_cli import run

from clarity.config import ConfigError, load_config
from clarity.engine import analyze

COMPOSITE = {
    "id": "combo", "category": "composite", "backend": "composite", "count_scope": "sentence",
    "max_per_scope": 0, "requires_all": [{"rule": "hedge"}, {"rule": "intensifier"}],
}  # fmt: skip
BOTH = "This is arguably a genuinely good plan."


def cfg(*rules):
    return load_config(text=yaml.safe_dump({"rules": list(rules)}))


def find(result, rule):
    return [f for f in result["findings"] if f["rule"] == rule]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"requires_all": [{"rule": "nope"}]}, "unknown or disabled rule 'nope'"),
        ({"requires_all": [{"rule": "combo"}]}, "refers to the rule itself"),
        ({"requires_all": [{"rule": "hedge", "min_count": 0}]}, "min_count"),
        ({"requires_all": [], "requires_any": []}, "needs requires_all or requires_any"),
    ],
)
def test_composites_reject_bad_members_at_load_naming_the_rule(change, message):
    with pytest.raises(ConfigError, match=message) as exc:
        cfg({**COMPOSITE, **change})

    assert "rule combo" in str(exc.value)


def test_a_composite_cannot_reference_another_composite_or_a_disabled_rule():
    other = {**COMPOSITE, "id": "other"}
    outer = {**COMPOSITE, "id": "outer", "requires_all": [{"rule": "other"}]}

    with pytest.raises(ConfigError, match="composites cannot nest"):
        cfg(other, outer)

    with pytest.raises(ConfigError, match="unknown or disabled"):
        cfg({"id": "hedge", "enabled": False}, COMPOSITE)


def test_requires_fields_belong_to_composites_only():
    with pytest.raises(ConfigError, match="only valid with backend: composite"):
        cfg({"id": "hedge", "requires_all": [{"rule": "intensifier"}]})


@pytest.mark.parametrize(
    "bad",
    [
        {"suppress_if": [{"near": {"pos": "PROPN"}}]},
        {"suppress_if": [{"near": {"pos": "PROPN", "pattern": "x", "within": 3}}]},
        {"suppress_if": [{"near": {"pattern": "[", "within": 3}}]},
        {"suppress_if": [{"in_scope": {"count_scope": "sentence", "rule": "nope"}}]},
        {"suppress_if": [{"metric": "nope", "op": "lt", "value": 1}]},
        {"active_when": {"metric": "modal_density", "op": "near", "value": 1}},
        {"allowance_when": [{"over_allowance": "hedges", "max_per_1k": 0}]},
        {"allowance_when": [{"over_allowance": "intensifiers", "max_per_scope": 0}]},
    ],
)
def test_condition_fields_that_do_not_resolve_fail_at_load(bad):
    with pytest.raises(ConfigError, match="rule hedge"):
        cfg({"id": "hedge", **bad})


def test_a_composite_is_one_finding_with_its_members_as_children():
    result = analyze(BOTH, config=cfg(COMPOSITE))
    found = find(result, "combo")

    assert len(found) == 1
    assert {c["rule"] for c in found[0]["children"]} == {"hedge", "intensifier"}
    assert not find(result, "hedge") and not find(result, "intensifier")
    assert "arguably" in found[0]["span"]["text"] and "genuinely" in found[0]["span"]["text"]


def test_one_member_alone_does_not_fire_and_stays_a_normal_finding():
    result = analyze("This is arguably a good plan.", config=cfg(COMPOSITE))

    assert not find(result, "combo") and find(result, "hedge")


def test_min_count_and_requires_none_and_requires_any():
    twice = {**COMPOSITE, "requires_all": [{"rule": "hedge", "min_count": 2}]}
    two = "This is arguably somewhat useful."

    assert find(analyze(two, config=cfg(twice)), "combo")
    assert not find(analyze("This is arguably a good plan.", config=cfg(twice)), "combo")

    none = {
        **COMPOSITE,
        "requires_all": [{"rule": "hedge"}],
        "requires_none": [{"rule": "intensifier"}],
    }

    assert not find(analyze(BOTH, config=cfg(none)), "combo")
    assert find(analyze("This is arguably a good plan.", config=cfg(none)), "combo")

    anyof = {
        **COMPOSITE,
        "requires_all": [],
        "requires_any": [{"rule": "hedge"}, {"rule": "intensifier"}],
    }

    assert find(analyze("This is a genuinely good plan.", config=cfg(anyof)), "combo")


def test_composite_scope_is_respected():
    para = {**COMPOSITE, "count_scope": "paragraph"}
    split = "This is arguably fine.\n\nThis is genuinely fine."

    assert not find(analyze(split, config=cfg(COMPOSITE)), "combo")
    assert not find(analyze(split, config=cfg(para)), "combo")
    assert find(analyze("This is arguably fine. It is genuinely fine.", config=cfg(para)), "combo")


def test_active_when_switches_a_rule_off_unless_the_metric_holds():
    gate = {"metric": "modal_density", "op": "gt", "value": 5}
    rule = {"id": "intensifier", "active_when": gate}
    plain = "It is genuinely good."
    modal = "It would be genuinely good. We could ship it. They should test it."

    assert not find(analyze(plain, config=cfg(rule)), "intensifier")
    assert find(analyze(modal, config=cfg(rule)), "intensifier")
    assert (
        analyze(plain, config=cfg(rule), trace=True)["trace"]["inactive"][0]["rule"]
        == "intensifier"
    )


def test_allowance_when_a_metric_holds_replaces_the_allowance():
    rule = {"id": "intensifier", "max_per_1k": 0,
            "allowance_when": [{"metric": "modal_density", "op": "gt", "value": 5,
                                "max_per_1k": 1000}]}  # fmt: skip
    plain = "It is genuinely good."
    modal = "It would be genuinely good. We could ship it. They should test it."

    assert find(analyze(plain, config=cfg(rule)), "intensifier")[0]["over_allowance"] is True
    assert find(analyze(modal, config=cfg(rule)), "intensifier")[0]["over_allowance"] is False


def test_allowance_when_another_category_is_over_tightens_this_rule():
    tighter = {"over_allowance": "corporate-vocabulary", "max_per_1k": 0}
    rule = {"id": "escalation-phrase", "max_per_1k": 1000, "allowance_when": [tighter]}
    text = "More than that, it is good. We leverage tools."

    plain = analyze("More than that, it is good.", config=cfg(rule))
    tight = analyze(text, config=cfg(rule))

    assert find(plain, "escalation-phrase")[0]["over_allowance"] is False
    assert find(tight, "escalation-phrase")[0]["over_allowance"] is True


def test_suppress_if_near_lemma_pattern_in_scope_and_metric():
    base = {"id": "intensifier", "max_per_1k": 0}
    text = "It is genuinely [1] good. It is a truly fine plan today."
    pattern = {**base, "suppress_if": [{"near": {"pattern": r"\[\d+\]", "within": 3}}]}
    lemma = {**base, "suppress_if": [{"near": {"lemma": "fine", "within": 2}}]}
    scope = {**base, "suppress_if": [{"in_scope": {"count_scope": "sentence", "rule": "hedge"}}]}
    metric = {**base, "suppress_if": [{"metric": "modal_density", "op": "lt", "value": 100}]}

    assert [f["span"]["text"] for f in find(analyze(text, config=cfg(pattern)), "intensifier")] == [
        "truly"
    ]
    assert [f["span"]["text"] for f in find(analyze(text, config=cfg(lemma)), "intensifier")] == [
        "genuinely"
    ]
    assert (
        len(find(analyze("It is arguably genuinely good.", config=cfg(scope)), "intensifier")) == 0
    )
    assert len(find(analyze("It is genuinely good.", config=cfg(scope)), "intensifier")) == 1
    assert not find(analyze(text, config=cfg(metric)), "intensifier")


def test_a_suppressed_match_consumes_no_allowance_and_is_reported_in_the_trace():
    text = "Studies show that NASA is right. Studies show it works."
    result = analyze(text, config=cfg(), trace=True)
    suppressed = result["trace"]["suppressed"]

    assert {s["rule"] for s in suppressed} == {"weasel-attribution"}
    assert "near" in suppressed[0]["condition"]


def test_explain_shows_composite_member_states(tmp_path, monkeypatch):
    rules = tmp_path / ".clarity" / "rules"
    rules.mkdir(parents=True)
    (rules / "combo.yml").write_text(
        yaml.safe_dump({"rules": [{**COMPOSITE, "experimental": True}]})
    )
    monkeypatch.setenv("CLARITY_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    both = run(["explain", "combo", BOTH])[1]
    one = run(["explain", "combo", "This is arguably a good plan."])[1]

    assert "hedge ✓ (1 of 1)" in both and "intensifier ✓ (1 of 1)" in both and "FIRES" in both
    assert "intensifier ✗ (0 of 1)" in one and "no match" in one


def test_explain_for_a_suppressed_match_names_the_condition():
    code, out, _ = run(["explain", "weasel-attribution", "Studies show that NASA says it works."])

    assert code == 0 and "SUPPRESSED" in out and "near pos" in out
