"""The shared lemma and overlap utility."""

import pytest

from clarity.nlp import get_nlp
from clarity.overlap import content_lemmas, overlap, paragraph_idf


def lemmas(text: str) -> set[str]:
    return content_lemmas(get_nlp()(text))


def test_content_lemmas_keeps_content_pos_and_drops_stopwords():
    assert lemmas("The cats were chasing quickly.") == {"cat", "chase", "quickly"}


def test_content_lemmas_of_a_span_ignores_the_rest_of_the_doc():
    doc = get_nlp()("Dogs bark. Birds sing loudly.")
    second = list(doc.sents)[1]

    assert content_lemmas(second) == {"bird", "sing", "loudly"}


def test_overlap_is_plain_jaccard_without_idf():
    assert overlap({"a", "b", "c"}, {"b", "c", "d"}) == pytest.approx(0.5)
    assert overlap(set(), set()) == 0.0


def test_idf_weight_makes_a_shared_rare_lemma_count_more_than_a_shared_topic_lemma():
    idf = {"image": 0.0, "cache": 2.0, "x": 1.0, "y": 1.0}
    topic = overlap({"image", "x"}, {"image", "y"}, idf)
    rare = overlap({"cache", "x"}, {"cache", "y"}, idf)

    assert topic == 0.0
    assert rare == pytest.approx(0.5)


def test_overlap_falls_back_to_plain_jaccard_when_every_weight_is_zero():
    idf = {"a": 0.0, "b": 0.0}

    assert overlap({"a"}, {"a", "b"}, idf) == pytest.approx(0.5)


def test_paragraph_idf_zeroes_a_lemma_found_in_every_paragraph():
    paragraphs = [{"image", "build"}, {"image", "ship"}, {"image", "run"}]
    idf = paragraph_idf(paragraphs)

    assert idf["image"] == 0.0
    assert idf["build"] > 0.0
