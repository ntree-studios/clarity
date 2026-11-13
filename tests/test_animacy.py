"""The animacy predicate, tested independently of the rules."""

import pytest

from clarity.animacy import is_animate
from clarity.nlp import get_nlp


def subject(sentence: str):
    doc = get_nlp()(sentence)

    return next(t for t in doc if t.dep_ == "nsubj")


@pytest.mark.parametrize(
    "sentence",
    [
        "The committee decided to wait.",
        "Washington insists on it.",
        "She knows the answer.",
        "They want a refund.",
        "The engineer chose a framework.",
        "The team believes in it.",
        "The dog wants a walk.",
        "The company refuses to pay.",
        "Maria argues the point.",
        "Everyone knows that.",
    ],
)
def test_animate_subjects_pass(sentence):
    assert is_animate(subject(sentence)) is True


@pytest.mark.parametrize(
    "sentence",
    [
        "The architecture wants a single entry point.",
        "The code knows the schema.",
        "This constraint tells us nothing.",
        "The report says costs rose.",
        "The data wants more rows.",
        "The system decided to retry.",
        "The function expects an integer.",
        "It believes in nothing.",
    ],
)
def test_inanimate_subjects_fail(sentence):
    assert is_animate(subject(sentence)) is False
