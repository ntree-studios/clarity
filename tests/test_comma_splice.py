import pytest

from clarity.engine import analyze


def splices(text: str) -> list[dict]:
    return [f for f in analyze(text)["findings"] if f["rule"] == "comma-splice"]


def test_plain_splice_fires():
    assert splices("The build failed, the team fixed it.")


def test_comma_plus_conjunction_is_not_a_splice():
    assert not splices("The build failed, and the team fixed it.")


@pytest.mark.parametrize(
    "text",
    [
        # reporting verb taking a clausal complement
        "He said, the build failed.",
        "She believes, the release matters.",
        # split quotation
        '"The build failed," she said, "the team fixed it."',
        # fronted subordinate clause with an opener that carries no mark dependency
        "Once the build failed, the team fixed it.",
        "When the build failed, the team fixed it.",
        "If the build fails, the team fixes it.",
    ],
)
def test_guard_cases_do_not_fire(text):
    assert not splices(text)
