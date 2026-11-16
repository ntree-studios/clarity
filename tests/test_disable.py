"""--disable and --enable on check, score and topics."""

import json

from test_cli import EM, run

TEXT = (
    f"The new dashboard is a testament to our team {EM} and it plays a pivotal role. "
    "Simply restart the service."
)
CORPORATE = {"ai-lexicon-gpt4", "corporate-tier-a"}


def fired(*flags):
    code, out, err = run(["check", "-", "--format", "json", *flags], stdin=TEXT)

    assert code in (0, 1), err

    return {f["rule"] for f in json.loads(out)["findings"]}


def test_disable_takes_rule_and_category_ids_repeated_or_comma_separated():
    before = fired()

    assert {"em-dash", *CORPORATE} <= before
    assert not ({"em-dash", *CORPORATE} & fired("--disable", "em-dash,corporate-vocabulary"))
    assert not ({"em-dash", *CORPORATE}
                & fired("--disable", "em-dash", "--disable", "corporate-vocabulary"))  # fmt: skip


def test_enable_turns_on_an_off_by_default_rule_and_beats_a_disabled_category():
    assert "ease-words" not in fired()
    assert "ease-words" in fired("--enable", "ease-words")
    assert fired("--disable", "structural-tics", "--enable", "em-dash") & {"em-dash"}


def test_disabling_a_composite_member_switches_the_composite_off_too():
    assert "em-dash" not in fired("--disable", "significance-asserting,em-dash")


def test_score_and_topics_take_the_flags():
    code, plain, _ = run(["score", "-"], stdin=TEXT)
    _, switched, _ = run(["score", "-", "--disable", "em-dash,corporate-vocabulary"], stdin=TEXT)
    topics_code, _, err = run(["topics", "-", "--disable", "hedges"], stdin=TEXT)

    assert float(switched) > float(plain)
    assert topics_code == 0, err


def test_unknown_ids_are_an_error_naming_them():
    for command in ("check", "score", "topics"):
        code, _, err = run([command, "-", "--disable", "em-dash,nope", "--enable", "zz"],
                           stdin=TEXT)  # fmt: skip

        assert code == 2
        assert "nope" in err and "zz" in err
