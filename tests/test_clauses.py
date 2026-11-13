"""The shared clause segmentation utility. Four rules depend on it, so it is tested alone."""

import pytest

from clarity.clauses import clauses, is_clause_head
from clarity.nlp import get_nlp


def parse(text: str):
    return get_nlp()(text)


def heads(text: str) -> list[str]:
    return [c.head.text for c in clauses(parse(text))]


def test_simple_sentence_is_one_clause():
    assert heads("The build failed.") == ["failed"]


def test_coordination_with_a_shared_subject_is_one_clause():
    assert heads("She opened the door and walked in.") == ["opened"]


def test_coordination_with_two_subjects_is_two_clauses():
    assert heads("The build failed and the team fixed it.") == ["failed", "fixed"]


def test_relative_clause_is_its_own_clause_and_leaves_the_matrix():
    doc = parse("The engineer who wrote it left.")
    found = clauses(doc)

    assert sorted(c.head.text for c in found) == ["left", "wrote"]

    matrix = next(c for c in found if c.head.text == "left")
    relative = next(c for c in found if c.head.text == "wrote")

    assert {t.text for t in relative.tokens} >= {"who", "wrote", "it"}
    assert not {"who", "wrote"} & {t.text for t in matrix.tokens}


def test_fronted_subordinate_clause_is_its_own_clause():
    assert sorted(heads("When the build failed, the team fixed it.")) == ["failed", "fixed"]


def test_non_finite_complement_is_not_a_clause():
    assert heads("She decided to run.") == ["decided"]


def test_comma_splice_is_two_clauses():
    assert sorted(heads("The build failed, the team fixed it.")) == ["failed", "fixed"]


def test_verbless_fragment_is_one_clause_covering_the_sentence():
    doc = parse("Not fast.")
    found = clauses(doc)

    assert len(found) == 1
    assert found[0].head.text == "fast"
    assert [t.text for t in found[0].tokens] == ["Not", "fast", "."]


def test_clauses_never_overlap_and_come_in_document_order():
    doc = parse(
        "When the build failed, the lead said that the team, which had worked all night, "
        "wanted to fix it because they believed the release mattered."
    )
    found = clauses(doc)
    seen: set[int] = set()

    for c in found:
        indexes = {t.i for t in c.tokens}

        assert not indexes & seen
        seen |= indexes

    assert [c.start for c in found] == sorted(c.start for c in found)
    assert len(found) >= 5


def test_clause_exposes_its_span_and_first_token():
    doc = parse("The build failed and the team fixed it.")
    second = clauses(doc)[1]

    assert second.span.text.startswith("and the team") or second.span.text.startswith("the team")
    assert second.first.text in {"and", "the"}


def test_is_clause_head_requires_a_verb_with_a_subject():
    doc = parse("The build failed to start.")
    failed = next(t for t in doc if t.text == "failed")
    start = next(t for t in doc if t.text == "start")

    assert is_clause_head(failed)
    assert not is_clause_head(start)


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_input_has_no_clauses(text):
    assert clauses(parse(text)) == []
