import pytest

from clarity.config import load_config
from clarity.engine import analyze

FILLER = "The team shipped the build on time. "


def fired(text: str, **kw) -> set[str]:
    return {f["rule"] for f in analyze(text, **kw)["findings"]}


def long_doc(sentence: str, count: int) -> str:
    return (sentence + " ") * count + FILLER * 150


@pytest.mark.parametrize(
    "verb",
    ["says", "knows", "wants", "sees", "loves", "believes", "decides", "hears", "fears"],
)
def test_verb_sets_cover_all_five_groups(verb):
    assert "false-agency" in fired(f"The architecture {verb} a single entry point.")


def test_document_source_with_speech_verb_hits_only_the_exemption_rule():
    assert fired("The study claims costs rose.") == {"false-agency-document-source"}


def test_document_source_with_non_speech_verb_is_main_rule():
    got = fired("The report wants more money.")

    assert "false-agency" in got
    assert "false-agency-document-source" not in got


def test_data_soft_verbs_hit_only_soft_rule():
    assert fired("The data suggest a trend.") == {"false-agency-data-soft"}


@pytest.mark.parametrize("verb", ["wants", "loves", "sees", "fears", "chooses"])
def test_data_volition_emotion_perception_hit_only_hard_rule(verb):
    assert fired(f"The data {verb} more rows.") == {"false-agency-data-hard"}


def test_data_with_cognition_verb_is_main_rule():
    assert fired("The data knows the answer.") == {"false-agency"}


def test_exemption_severities_and_allowances():
    rules = {r.id: r for r in load_config(None).rules}

    assert rules["false-agency-document-source"].max_per_1k == 4
    assert rules["false-agency-document-source"].severity == "info"
    assert rules["false-agency-data-soft"].max_per_1k == 2
    assert rules["false-agency-data-hard"].max_per_1k == 0
    assert rules["false-agency-data-hard"].severity == "warning"
    assert rules["false-agency"].max_per_1k == 0
    assert rules["false-agency"].confidence == "inferred"


def test_document_source_allowance_is_four_per_1k():
    res = analyze(long_doc("The report says costs rose.", 5))
    hits = [f for f in res["findings"] if f["rule"] == "false-agency-document-source"]

    assert len(hits) == 5
    assert [f["over_allowance"] for f in hits] == [False] * 4 + [True]


def test_data_soft_allowance_is_two_per_1k():
    res = analyze(long_doc("The data suggest a trend.", 3))
    hits = [f for f in res["findings"] if f["rule"] == "false-agency-data-soft"]

    assert [f["over_allowance"] for f in hits] == [False, False, True]


def test_false_agency_is_filtered_by_min_confidence_exact():
    text = "The architecture wants a single entry point."

    assert "false-agency" in fired(text)
    assert not {r for r in fired(text, min_confidence="exact") if r.startswith("false-agency")}


def test_category_numbers():
    cats = load_config(None).categories

    assert [cats[n].id for n in (10, 11, 12, 13)] == [
        "false-agency",
        "verbosity",
        "sentence-flow",
        "watchlist",
    ]
