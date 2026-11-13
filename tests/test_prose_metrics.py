"""Unscored document measurements."""

import pytest

from clarity.config import load_config
from clarity.engine import analyze

CONNECTED = (
    "The cache stores hot keys. The keys expire after an hour. An hour is long for a cache. "
    "The cache then refills. Refills are cheap."
)
DISCONNECTED = (
    "Rain fell all morning. Crews unloaded oranges. A gull watched. The foreman counted receipts. "
    "Children chased pigeons. An engine coughed."
)


def metrics(text: str, **kw) -> dict:
    return analyze(text, **kw)["prose_metrics"]


def test_every_metric_is_reported_and_marked_unscored():
    m = metrics(CONNECTED)

    assert m["weight"] == 0.0
    assert {
        "sentence_length_variance",
        "paragraph_length_distribution",
        "lexical_diversity",
        "content_word_ratio",
        "given_new_ordering",
        "referential_density",
        "mean_concreteness",
    } <= set(m["metrics"])


def test_prose_metrics_never_change_the_style_score():
    cfg = load_config(text="prose_metrics: {weight: 5.0}")

    assert analyze(CONNECTED, config=cfg)["score"] == analyze(CONNECTED)["score"]


def test_given_new_ordering_separates_connected_from_disconnected_prose():
    linked = metrics(CONNECTED)["metrics"]["given_new_ordering"]["proportion"]
    unlinked = metrics(DISCONNECTED)["metrics"]["given_new_ordering"]["proportion"]

    assert linked >= 0.75
    assert unlinked <= 0.25


def test_given_new_ordering_looks_back_two_sentences_and_skips_the_first():
    text = "Alpha runs fast. Beta waits. Alpha stops. Gamma starts. Delta ends."
    result = metrics(text)["metrics"]["given_new_ordering"]

    assert result["evaluated"] == 4
    assert result["proportion"] == pytest.approx(0.25)


def test_lexical_diversity_is_length_independent_and_orders_repetition_below_variety():
    repetitive = "the cat sat on the mat. " * 40
    varied = (
        "Rain fell across the harbor while crews unloaded oranges, tin, rope, nets, barrels, "
        "timber and slate. A foreman counted receipts; children chased pigeons; engines coughed "
        "and ferries left with passengers carrying umbrellas, violins, and ledgers. "
    ) * 2
    low = metrics(repetitive)["metrics"]["lexical_diversity"]["mtld"]
    high = metrics(varied)["metrics"]["lexical_diversity"]["mtld"]

    assert low < high


def test_sentence_length_variance_reports_mean_and_sd():
    result = metrics("One two three. One two three four five. One.")
    m = result["metrics"]["sentence_length_variance"]

    assert m["mean"] == pytest.approx(3.0)
    assert m["sd"] == pytest.approx(1.63, abs=0.01)


def test_paragraph_distribution_counts_blank_line_blocks_and_ignores_headings():
    m = metrics("# Title\n\nOne two three.\n\nFour five six seven eight.\n")["metrics"][
        "paragraph_length_distribution"
    ]

    assert m["count"] == 2
    assert (m["min"], m["max"]) == (3, 5)


def test_content_word_ratio_and_concreteness_and_referential_density():
    m = metrics("The dog chased the cat. It ran away.")["metrics"]

    assert m["content_word_ratio"]["ratio"] > 0.5
    assert m["mean_concreteness"]["mean"] > 3.5
    assert m["referential_density"]["per_1k"] > 0
    assert m["referential_density"]["mean_antecedent_distance"] is not None


def test_text_report_prints_the_block_after_readability_and_says_unscored():
    from test_cli import run

    _, out, _ = run(["check", "-"], stdin=CONNECTED)

    assert "PROSE METRICS" in out
    assert "unscored" in out
    assert out.index("READABILITY") < out.index("PROSE METRICS")


def test_novelty_rate_names_the_paragraph_that_adds_nothing_new():
    padded = "The cache stores hot keys. The cache stores hot keys. The cache stores hot keys."
    fresh = "Rain fell. Crews unloaded oranges. A gull watched. Children chased pigeons."
    m = metrics(f"{fresh}\n\n{padded}")["metrics"]["novelty_rate"]

    assert m["paragraphs_scored"] == 2
    assert m["lowest_paragraphs"][0] == {"line": 3, "rate": 0.0}
    assert m["per_sentence"] > 0


def test_novelty_rate_skips_single_sentence_paragraphs():
    m = metrics("One sentence only.\n\nAnother lone sentence.")["metrics"]["novelty_rate"]

    assert m["paragraphs_scored"] == 0
    assert m["per_sentence"] is None
