"""count_scope, position, load-time validation, and the inert-rule notice."""

import pytest

from clarity.config import ConfigError, load_config
from clarity.engine import analyze

FILLER = "The team shipped the build on time. "


def rule_yaml(**fields) -> str:
    body = {"id": "r", "category": "hedges", "phrases": ["really"], "match": "lower", **fields}
    items = ", ".join(f"{k}: {v!r}" if isinstance(v, str) else f"{k}: {v}" for k, v in body.items())

    return "rules:\n  - {" + items.replace("'", '"') + "}\n"


def run(text: str, **fields):
    return analyze(text, config=load_config(text=rule_yaml(**fields)))


def mine(result, rule="r"):
    return [f for f in result["findings"] if f["rule"] == rule]


# ---- validation at load -------------------------------------------------------------------


def test_max_per_1k_on_a_non_document_scope_is_rejected_with_the_rule_id():
    with pytest.raises(ConfigError, match=r"\br\b.*max_per_1k"):
        load_config(text=rule_yaml(count_scope="section", max_per_1k=1))


def test_max_per_scope_on_a_document_scope_is_rejected_with_the_rule_id():
    with pytest.raises(ConfigError, match=r"\br\b.*max_per_scope"):
        load_config(text=rule_yaml(count_scope="document", max_per_scope=1))


def test_max_per_scope_on_the_default_document_scope_is_rejected():
    with pytest.raises(ConfigError, match="max_per_scope"):
        load_config(text=rule_yaml(max_per_scope=1))


def test_the_old_scope_field_is_rejected_with_a_pointer_to_the_new_fields():
    with pytest.raises(ConfigError, match=r"\br\b.*count_scope.*position"):
        load_config(text=rule_yaml(scope="clause"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("count_scope", "page"), ("position", "middle")],
)
def test_unknown_scope_and_position_values_are_rejected(field, value):
    with pytest.raises(ConfigError, match=field):
        load_config(text=rule_yaml(**{field: value}))


def test_defaults_are_document_scope_and_anywhere():
    rule = next(r for r in load_config(text=rule_yaml(max_per_1k=1)).rules if r.id == "r")

    assert (rule.count_scope, rule.position) == ("document", "anywhere")


# ---- position filters ---------------------------------------------------------------------


def test_sentence_initial_keeps_only_the_first_token_of_a_sentence():
    assert mine(run("Really, it works.", position="sentence-initial"))
    assert not mine(run("It really works.", position="sentence-initial"))


def test_clause_initial_accepts_a_later_clause_but_not_mid_clause():
    text = "The build failed, really the team fixed it."

    assert mine(run(text, position="clause-initial"))
    assert not mine(run("The team really fixed it.", position="clause-initial"))


def test_sentence_final_keeps_the_last_content_token():
    assert mine(run("It works really.", position="sentence-final"))
    assert not mine(run("Really it works.", position="sentence-final"))


def test_section_final_keeps_matches_inside_the_last_sentence_of_a_section():
    doc = {"sections": [{"title": "A", "text": "We are really done. Next thing."},
                        {"title": "B", "text": "More text, really done here."}]}  # fmt: skip
    found = mine(run(doc, position="section-final"))

    assert [(f["section"], f["field"], f["line"]) for f in found] == [("1", "text", 1)]


def test_a_match_failing_the_position_test_does_not_consume_allowance():
    text = "It really works. Really, it works."
    result = run(text, position="sentence-initial", max_per_1k=1000)

    assert len(mine(result)) == 1
    assert mine(result)[0]["over_allowance"] is False


# ---- count_scope --------------------------------------------------------------------------


def test_clause_scope_counts_raw_per_clause_not_per_1k():
    result = run("It is really really good.", count_scope="clause", max_per_scope=1)

    assert [f["over_allowance"] for f in mine(result)] == [False, True]


def test_clause_scope_gives_each_clause_its_own_allowance():
    text = "The build is really fine, and the tests are really green."
    result = run(text, count_scope="clause", max_per_scope=1)

    assert [f["over_allowance"] for f in mine(result)] == [False, False]


def test_sentence_scope_allowance_is_per_sentence():
    text = "It is really fine. It is really green. It is really really done."
    result = run(text, count_scope="sentence", max_per_scope=1)

    assert [f["over_allowance"] for f in mine(result)] == [False, False, False, True]


def test_paragraph_scope_allowance_is_per_blank_line_block():
    text = "It is really fine.\n\nIt is really green. It is really done."
    result = run(text, count_scope="paragraph", max_per_scope=1)

    assert [f["over_allowance"] for f in mine(result)] == [False, False, True]


def test_section_scope_allowance_is_per_section():
    doc = {"sections": [{"title": "A", "text": "Really fine. Really green."},
                        {"title": "B", "text": "Really done."}]}  # fmt: skip
    result = run(doc, count_scope="section", max_per_scope=1)

    assert [f["over_allowance"] for f in mine(result)] == [False, True, False]


def test_category_over_by_sums_per_scope_overs_without_dividing_by_length():
    text = "It is really really good. " + FILLER * 200
    result = run(text, count_scope="clause", max_per_scope=1)
    cat = next(c for c in result["categories"] if c["id"] == "hedges")

    assert cat["over_by"] == 1


# ---- inert section rules ------------------------------------------------------------------


def test_plain_text_disables_section_rules_and_says_so():
    result = analyze("Pick tools. It depends.")
    disabled = {d["rule"]: d["reason"] for d in result["disabled_rules"]}

    assert {"section-restatement", "it-depends-conclusion"} <= set(disabled)
    assert "section tree" in disabled["it-depends-conclusion"]
    assert not [f for f in result["findings"] if f["rule"] == "it-depends-conclusion"]


def test_a_section_tree_keeps_section_rules_active():
    result = analyze({"title": "Choice", "text": "Pick tools. It depends."})

    assert result["disabled_rules"] == []
    assert [f for f in result["findings"] if f["rule"] == "it-depends-conclusion"]


def test_markdown_headings_in_a_plain_string_are_plain_text():
    result = analyze("# Choice\n\nPick tools. It depends.")

    assert {d["rule"] for d in result["disabled_rules"]} >= {"it-depends-conclusion"}


def test_paragraph_final_position_keeps_only_the_last_sentence_of_each_paragraph():
    text = "Really good. Fine. Really bad.\n\nReally odd. Done."

    assert len(mine(run(text))) == 3
    assert [f["line"] for f in mine(run(text, position="paragraph-final"))] == [1]


def test_paragraph_final_is_a_valid_position_and_unknown_ones_still_fail():
    load_config(text=rule_yaml(position="paragraph-final"))

    with pytest.raises(ConfigError, match="position"):
        load_config(text=rule_yaml(position="paragraph-start"))


# ---- the migrated pack --------------------------------------------------------------------



def test_two_hedges_in_one_clause_cost_score_but_one_does_not():
    two = analyze("This is arguably somewhat useful.")
    one = analyze("This is arguably useful.")
    def cost(r):
        return next(c for c in r["categories"] if c["id"] == "hedges")["penalty"]


    assert cost(two) > cost(one)
    assert [f["over_allowance"] for f in two["findings"] if f["rule"] == "hedge-stacking"] == [
        False,
        True,
    ]


# ---- applies_to ---------------------------------------------------------------------------


def test_applies_to_limits_a_rule_to_the_fields_it_names():
    doc = {"title": "Really done", "text": "It is really fine.", "items": ["Really good"]}
    fields_ = {f["field"] for f in mine(run(doc))}
    only_text = {f["field"] for f in mine(run(doc, applies_to=["text"]))}
    only_titles = {f["field"] for f in mine(run(doc, applies_to=["title"]))}

    assert fields_ == {"title", "text", "items[0]"}
    assert (only_text, only_titles) == ({"text"}, {"title"})


def test_applies_to_must_name_known_fields():
    with pytest.raises(ConfigError, match="applies_to"):
        load_config(text=rule_yaml(applies_to=["heading"]))

    with pytest.raises(ConfigError, match="applies_to"):
        load_config(text=rule_yaml(applies_to=[]))


@pytest.mark.parametrize("title", [
    "Three teams, one shared vision",
    "Roadmap: four steps, each one building on the last",
    "What we found, and why it counts",
])  # fmt: skip
def test_sentence_rules_skip_a_title_checked_alone(title):
    from clarity.config import load_config as bundled

    cfg = bundled(None)
    text_only = {r.id for r in cfg.rules if r.applies_to == ["text"]}
    found = analyze({"title": title}, config=cfg)["findings"]

    assert {"long-sentence", "fragment-triad", "comma-splice"} <= text_only
    assert not [f for f in found if f["rule"] in text_only]
    assert all(f["field"] == "title" for f in found)


def test_a_title_with_a_colon_is_one_sentence_for_sentence_rules():
    title = "Regional Freight Services: Annual Plan"
    result = analyze({"title": title}, config=load_config(None))
    ratio = [f for f in result["findings"] if f["rule"] == "function-word-ratio"]

    assert result["sentences"] == 1
    assert all(f["span"]["text"] == title for f in ratio)
