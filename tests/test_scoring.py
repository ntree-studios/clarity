import pytest

from clarity.ids import finding_id, normalize_span
from clarity.scoring import category_result, score_document


def test_allowance_arithmetic_four_found_one_allowed_over_by_three():
    # 1000 words, allowance 1 per 1k => 4 found, 1 allowed, over by 3
    res = category_result(
        cat_id="intensifiers", name="Intensifiers", found=4, words=1000,
        max_per_1k=1, weight=2.0, cap=30.0,
    )
    assert res["found"] == 4
    assert res["over_by"] == 3
    assert res["rate_per_1k"] == 4.0
    assert res["max_per_1k"] == 1
    assert res["penalty"] == 6.0
    assert res["capped"] is False


def test_under_allowance_scores_zero():
    res = category_result("c", "C", found=1, words=1000, max_per_1k=1, weight=5.0, cap=30.0)
    assert res["over_by"] == 0
    assert res["penalty"] == 0.0


def test_allowance_scales_with_document_length():
    # 2000 words, allowance 1/1k => 2 allowed
    res = category_result("c", "C", found=3, words=2000, max_per_1k=1, weight=1.0, cap=30.0)
    assert res["over_by"] == 1


def test_zero_tolerance_rule_penalizes_every_instance():
    res = category_result("c", "C", found=2, words=1000, max_per_1k=0, weight=1.0, cap=30.0)
    assert res["over_by"] == 2


def test_cap_limits_category_penalty():
    res = category_result("c", "C", found=50, words=1000, max_per_1k=0, weight=2.0, cap=10.0)
    assert res["penalty"] == 10.0
    assert res["capped"] is True


def test_zero_words_does_not_divide_by_zero():
    res = category_result("c", "C", found=0, words=0, max_per_1k=1, weight=1.0, cap=10.0)
    assert res["rate_per_1k"] == 0.0
    assert res["penalty"] == 0.0


def test_score_is_100_minus_penalties_floored_at_zero():
    cats = [{"penalty": 40.0}, {"penalty": 70.0}]
    assert score_document(cats) == 0
    assert score_document([{"penalty": 12.5}]) == 87.5
    assert score_document([]) == 100


def test_finding_id_stable_when_position_moves():
    a = finding_id("em-dash", "He left — quickly.")
    b = finding_id("em-dash", "He left — quickly.")
    assert a == b


def test_finding_id_differs_by_rule_and_span():
    assert finding_id("a", "x y") != finding_id("b", "x y")
    assert finding_id("a", "x y") != finding_id("a", "x z")


def test_normalize_span_collapses_whitespace_and_case():
    assert normalize_span("  Hello \n  WORLD ") == "hello world"
    assert finding_id("r", "Hello  World") == finding_id("r", "hello world")


@pytest.mark.parametrize("span", ["", "   "])
def test_empty_span_still_hashes(span):
    assert len(finding_id("r", span)) == 12
