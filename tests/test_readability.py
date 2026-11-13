import pytest

from clarity.config import load_config
from clarity.engine import analyze
from clarity.readability import count_syllables, metrics

TEXT = "The cat sat on the mat."


@pytest.mark.parametrize(
    ("word", "count"),
    [("cat", 1), ("table", 2), ("banana", 3), ("readability", 5), ("determination", 5), ("the", 1)],
)
def test_syllable_counts(word, count):
    assert count_syllables(word) == count


def test_metrics_match_published_formulas_on_a_known_sentence():
    m = metrics(words=6, sentences=1, syllables=6, letters=17, complex_words=0)

    assert m["flesch_reading_ease"] == pytest.approx(116.145, rel=1e-3)
    assert m["flesch_kincaid_grade"] == pytest.approx(-1.45, rel=1e-3)
    assert m["gunning_fog"] == pytest.approx(2.4, rel=1e-3)
    assert m["smog"] == pytest.approx(3.1291, rel=1e-3)
    assert m["ari"] == pytest.approx(-5.085, rel=1e-2)
    assert m["coleman_liau"] == pytest.approx(-4.07, rel=1e-2)


def test_result_has_readability_object_with_band():
    r = analyze(TEXT)["readability"]

    assert set(r["metrics"]) == {
        "flesch_reading_ease",
        "flesch_kincaid_grade",
        "gunning_fog",
        "smog",
        "coleman_liau",
        "ari",
    }
    assert r["target_grade"] == [8, 12]
    assert r["inside_band"] is False
    assert r["fail_outside_band"] is False


def test_band_comes_from_config():
    cfg = load_config(text="readability: {target_grade: [-10, 5], fail_outside_band: true}")
    r = analyze(TEXT, config=cfg)["readability"]

    assert r["target_grade"] == [-10, 5]
    assert r["inside_band"] is True
    assert r["fail_outside_band"] is True


def test_readability_never_changes_the_style_score():
    a = analyze(TEXT)["score"]
    cfg = load_config(text="readability: {target_grade: [30, 40], fail_outside_band: true}")

    assert analyze(TEXT, config=cfg)["score"] == a
