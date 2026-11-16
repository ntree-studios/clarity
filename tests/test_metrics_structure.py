"""Structure, variety, register and document metrics on known passages."""

import pytest

from clarity.config import load_config
from clarity.engine import analyze
from clarity.metrics import REGISTRY, Analysis, get_at, scalars
from clarity.nlp import get_nlp
from clarity.structure import from_tree, parse_doc


def a(text: str) -> Analysis:
    return Analysis(get_nlp()(text), text)


def tree(t: dict) -> Analysis:
    s = from_tree(t)

    return Analysis(parse_doc(get_nlp(), s), s.text, structure=s)


def test_sentence_types_follow_independent_and_dependent_clauses():
    m = a(
        "We ship. We ship and they test. We ship because it works. "
        "We ship and they test because it works. Fast builds."
    ).get("sentence_type_distribution")

    assert m["counts"] == {"simple": 1, "compound": 1, "complex": 1, "compound-complex": 1,
                           "fragment": 1}  # fmt: skip


def test_subordination_and_clause_counts():
    m = a("We ship because it works. We stop.")

    assert m.get("subordination_index")["value"] == 0.5
    assert m.get("clauses_per_sentence")["value"] == 1.5


def test_dependency_depth_separates_flat_from_nested_sentences():
    flat = a("Tea is hot. Milk is cold.").get("mean_dependency_depth")["value"]
    deep = a("The man who said that the plan that we made would work left.").get(
        "mean_dependency_depth"
    )["value"]

    assert deep > flat


def test_openers_and_paragraph_opener_repetition():
    m = a("The cat sat. Then it left. Because it rained, we stayed.").get(
        "sentence_opener_distribution"
    )

    assert m["counts"]["subject"] == 1 and m["counts"]["adverbial"] == 1
    assert m["counts"]["subordinate-clause"] == 1
    paragraphs = "The cat sat.\n\nThe dog ran.\n\nThen birds flew."

    assert a(paragraphs).get("paragraph_opener_repetition")["value"] == 0.5


def test_voice_modals_and_noun_verb_balance():
    text = "The report was written by Ana. We would ship it. It might fail."

    assert a(text).get("voice_distribution")["passive"] == 1
    assert a(text).get("modal_density")["count"] == 2
    assert a("Tests and builds run.").get("nominal_verbal_ratio")["value"] == 2.0


def test_tense_shift_inside_a_paragraph_is_counted():
    assert a("We shipped it. We ship it. We shipped again.").get("tense_consistency")["shifts"] == 2
    assert a("We shipped it.\n\nWe ship it.").get("tense_consistency")["shifts"] == 0


def test_hapax_and_pronoun_antecedent_distance():
    assert a("A cat saw a cat.").get("hapax_ratio")["value"] == 0.33

    near = a("The plan failed. It was late.").get("pronoun_antecedent_distance")

    assert near["mean"] == 3 and near["unresolved"] == 0


def test_document_structure_metrics_read_the_tree():
    an = tree({"title": "A", "sections": [
        {"sections": [{"title": "B", "text": "Body."}]},
        {"title": "C"},
        {"title": "D", "text": "Text.", "items": ["Fix it", "Fixing it"]},
    ]})  # fmt: skip

    assert an.get("heading_hierarchy")["skipped_levels"] == 1
    assert an.get("heading_hierarchy")["single_child"] == 1
    assert an.get("heading_hierarchy")["empty"] == 1
    assert an.get("list_parallelism")["mismatched"] == 1


def test_markdown_in_a_plain_string_is_plain_text():
    an = a("# A\n\n- x\n- y\n")

    assert an.get("heading_hierarchy")["headings"] == 0
    assert an.get("list_parallelism")["lists"] == 0


def test_a_metric_can_be_read_over_one_paragraph_but_not_where_unsupported():
    an = a("We ship because it works.\n\nWe stop.")
    first = an.sentences[0]

    assert get_at(an, "subordination_index", first)["value"] == 1.0

    with pytest.raises(ValueError, match="document scope"):
        get_at(an, "novelty_rate", first)


def test_every_default_report_metric_is_registered_and_tracks_scalars():
    report = load_config(None).prose_metrics["report"]
    values = scalars(a("We ship it. They test it because it works."))

    assert set(report) <= set(REGISTRY)
    assert values and all(isinstance(v, float) for v in values.values())
    assert set(analyze("We ship it.")["prose_metrics"]["metrics"]) >= set(report)
