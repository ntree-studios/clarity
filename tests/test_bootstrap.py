"""A scripted bootstrap session over STDIO on two fixture corpora."""

import json
import os
import sys

import pytest
from test_mcp import payload, start

GOOD_LINES = [
    "The team shipped the build on Tuesday after the tests passed.",
    "Rain fell across the harbor and the crews unloaded crates of oranges.",
    "She counted the receipts twice, then locked the office and walked home.",
    "The ferry left on schedule with a few passengers and a dog.",
    "He fixed the leaking tap before the guests arrived for dinner.",
]
BAD_LINES = [
    "We leverage robust and seamless tooling to empower every team.",
    "The team shipped the build on Tuesday after the tests passed.",
    "Our holistic approach will unlock value and streamline the workflow.",
    "The ferry left on schedule with a few passengers and a dog.",
    "It is a robust platform that will leverage cutting-edge methods.",
]
THE_TEAM = {"id": "the-team", "category": "hedges", "max_per_1k": 0, "phrases": ["the team"]}
CORPORATE = {
    "id": "corp-words", "category": "corporate-vocabulary", "max_per_1k": 0,
    "phrases": ["leverage", "robust", "seamless", "empower", "holistic"],
}  # fmt: skip


def corpus(folder, lines, docs, words_per_doc=700):
    folder.mkdir(parents=True)

    for n in range(docs):
        body, i = [], n

        while sum(len(s.split()) for s in body) < words_per_doc:
            body.append(lines[i % len(lines)])
            i += 1

        (folder / f"doc{n:02}.md").write_text("\n\n".join(body) + "\n", encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    good, bad, tiny = tmp_path / "good", tmp_path / "bad", tmp_path / "tiny"
    corpus(good, GOOD_LINES + [BAD_LINES[1]], docs=12)
    corpus(bad, BAD_LINES, docs=12)
    corpus(tiny, GOOD_LINES, docs=3, words_per_doc=100)
    work = tmp_path / "work"
    work.mkdir()
    env = {**os.environ, "CLARITY_HOME": str(tmp_path / "home"),
           "PYTHONPATH": os.pathsep.join(sys.path)}  # fmt: skip
    s = start(cwd=work, env=env)

    yield s, good, bad, tiny, work

    s.close()


def call(session, tool, /, **args):
    result = session.tool(tool, args)

    if result["isError"]:
        return True, result["content"][0]["text"]

    return False, payload(result)


def test_a_rule_under_the_ratio_floor_is_rejected_and_never_written(world):
    s, good, bad, _, work = world
    stats = call(s, "corpus_stats", path=str(good))[1]

    assert stats["documents"] == 12 and stats["reliability"] == "provisional"

    candidates = call(s, "suggest_rules", good_path=str(good), bad_path=str(bad))[1]["candidates"]

    assert "leverage" in {c["ngram"] for c in candidates}

    flat = call(s, "test_rule", rule_definition=THE_TEAM, good_path=str(good), bad_path=str(bad))[1]
    strong = call(s, "test_rule", rule_definition=CORPORATE, good_path=str(good),
                  bad_path=str(bad))[1]  # fmt: skip

    assert flat["verdict"] == "discard" and flat["ratio"] < 3.0
    assert strong["verdict"] == "keep" and strong["bad_rate_per_1k"] > 0
    assert strong["provisional"] is True

    failed, _ = call(s, "write_rules", rules=[THE_TEAM, CORPORATE], user_approved=False)

    assert failed
    assert not (work / ".clarity").exists()

    _, written = call(s, "write_rules", rules=[THE_TEAM, CORPORATE], user_approved=True)
    saved = (work / ".clarity" / "rules" / "bootstrap.yml").read_text()

    assert written["written"] == ["corp-words"]
    assert [r["id"] for r in written["rejected"]] == ["the-team"]
    assert "ratio" in written["rejected"][0]["reason"]
    assert "corp-words" in saved and "the-team" not in saved


def test_an_unmeasured_or_edited_rule_is_refused(world):
    s, good, bad, _, work = world
    call(s, "test_rule", rule_definition=CORPORATE, good_path=str(good), bad_path=str(bad))
    edited = {**CORPORATE, "phrases": ["leverage", "synergy"]}
    _, written = call(s, "write_rules", rules=[edited], user_approved=True)

    assert written["written"] == [] and "not measured" in written["rejected"][0]["reason"]
    assert not (work / ".clarity").exists()


def test_a_corpus_under_the_hard_floor_produces_no_ratio(world):
    s, good, _, tiny, _ = world
    failed, text = call(s, "test_rule", rule_definition=CORPORATE, good_path=str(good),
                        bad_path=str(tiny))  # fmt: skip

    assert failed and "at least 10 documents" in text

    failed, text = call(s, "suggest_rules", good_path=str(tiny), bad_path=str(good))

    assert failed and "5,000 words" in text


def test_fixtures_are_validated_then_written_and_clear_experimental(world):
    s, good, bad, _, work = world
    call(s, "test_rule", rule_definition=CORPORATE, good_path=str(good), bad_path=str(bad))
    call(s, "write_rules", rules=[CORPORATE], user_approved=True)
    fixtures = {
        "should_fire": ["We leverage the tool."],
        "should_not_fire": ["The ferry left at noon.", "A lever moved the stone."],
    }
    thin = {"should_fire": ["We leverage the tool."], "should_not_fire": ["Rain fell."]}

    assert call(s, "write_fixtures", rule_id="corp-words", fixtures=thin, user_approved=True)[0]

    wrong = {**fixtures, "should_not_fire": ["We leverage the tool.", "Rain fell."]}
    check = call(s, "validate_fixtures", rule_id="corp-words", fixtures=wrong)[1]

    assert check["all_passed"] is False

    ok = call(s, "write_fixtures", rule_id="corp-words", fixtures=fixtures, user_approved=True)[1]
    rules = (work / ".clarity" / "rules" / "bootstrap.yml").read_text()

    assert ok["experimental_cleared"] is True and "experimental" not in rules
    assert json.dumps(call(s, "list_rules")[1]).count("corp-words") == 1
    assert (work / ".clarity" / "rules" / "bootstrap.test.yml").is_file()


def test_find_matches_returns_real_lines_and_resources_are_readable(world):
    s, _, bad, _, _ = world
    hits = call(s, "find_matches", path=str(bad), rule_definition=CORPORATE, limit=3)[1]

    assert len(hits) == 3 and all(h["file"].endswith(".md") and h["line"] >= 1 for h in hits)

    uris = {r["uri"] for r in s.call("resources/list")["result"]["resources"]}

    assert {"clarity://config/resolved", "clarity://rules", "clarity://categories",
            "clarity://profiles", "clarity://schema/rule", "clarity://schema/fixture",
            "clarity://guide/authoring", "clarity://guide/calibration"} <= uris  # fmt: skip

    doc = s.call("resources/read", {"uri": "clarity://schema/rule"})["result"]["contents"][0][
        "text"
    ]

    assert "Rule schema" in doc

    one = s.call("resources/read", {"uri": "clarity://rules/em-dash"})["result"]["contents"][0][
        "text"
    ]

    assert "em-dash" in one


def test_the_three_prompts_state_that_clarity_measures_every_number(world):
    s = world[0]
    names = {p["name"] for p in s.call("prompts/list")["result"]["prompts"]}

    assert names == {"bootstrap_rules", "bootstrap_fixtures", "tune_rule", "bootstrap_composites"}

    paths = {"good_corpus_path": "/g", "bad_corpus_path": "/b"}
    args = {"bootstrap_rules": paths, "bootstrap_composites": paths,
            "bootstrap_fixtures": {"rule_id": "x"}, "tune_rule": {"rule_id": "x"}}  # fmt: skip

    for name, arguments in args.items():
        got = s.call("prompts/get", {"name": name, "arguments": arguments})["result"]
        text = got["messages"][0]["content"]["text"]

        assert "must come from a clarity tool call" in text
        assert "Do not present a ratio you did not receive from a tool call" in text


HEDGE_ALONE = "This is arguably a fine plan for the yard."
INTENSIFIER_ALONE = "It is genuinely good for the whole family."
BOTH_IN_ONE = "This is arguably a genuinely good plan for the harbor."
COMPOSITE = {
    "id": "hedge-and-intensify", "category": "composite", "backend": "composite",
    "count_scope": "sentence", "max_per_scope": 0,
    "requires_all": [{"rule": "hedge"}, {"rule": "intensifier"}],
}  # fmt: skip
EITHER = {**COMPOSITE, "id": "either", "requires_all": [],
          "requires_any": [{"rule": "hedge"}, {"rule": "intensifier"}]}  # fmt: skip


@pytest.fixture
def pair(tmp_path):
    good, bad, work = tmp_path / "good", tmp_path / "bad", tmp_path / "work"
    corpus(good, [*GOOD_LINES, HEDGE_ALONE, INTENSIFIER_ALONE], docs=12)
    corpus(bad, [*BAD_LINES, HEDGE_ALONE, INTENSIFIER_ALONE, BOTH_IN_ONE, BOTH_IN_ONE], docs=12)
    work.mkdir()
    env = {**os.environ, "CLARITY_HOME": str(tmp_path / "home"),
           "PYTHONPATH": os.pathsep.join(sys.path)}  # fmt: skip
    s = start(cwd=work, env=env)

    yield s, good, bad, work

    s.close()


def test_a_composite_must_beat_its_members_before_it_can_be_written(pair):
    s, good, bad, work = pair
    wins = call(s, "test_composite", rule_definition=COMPOSITE, good_path=str(good),
                bad_path=str(bad))[1]  # fmt: skip
    ties = call(s, "test_composite", rule_definition=EITHER, good_path=str(good),
                bad_path=str(bad))[1]  # fmt: skip

    assert {m["rule"] for m in wins["members"]} == {"hedge", "intensifier"}
    assert wins["beats_members"] is True and wins["verdict"] == "keep"
    assert ties["beats_members"] is False and ties["verdict"] == "discard"
    assert ties["reason"]

    same = {
        **COMPOSITE,
        "id": "same",
        "requires_all": [],
        "requires_any": [{"rule": "corporate-tier-a"}],
    }
    equal = call(s, "test_composite", rule_definition=same, good_path=str(good),
                 bad_path=str(bad))[1]  # fmt: skip

    assert equal["beats_members"] is False and "does not beat" in equal["reason"]

    _, written = call(s, "write_rules", rules=[COMPOSITE, EITHER], user_approved=True)

    assert written["written"] == ["hedge-and-intensify"]
    assert [r["id"] for r in written["rejected"]] == ["either"]
    assert "either" not in (work / ".clarity" / "rules" / "bootstrap.yml").read_text()
    assert call(s, "test_composite", rule_definition={"id": "x"}, good_path=str(good),
                bad_path=str(bad))[0]  # fmt: skip


def test_metrics_baseline_and_drift_tools_and_resources(pair, tmp_path):
    s, good, bad, _ = pair
    metrics = call(s, "get_metrics", text=BOTH_IN_ONE)[1]

    assert "sentence_type_distribution" in metrics["metrics"]
    assert metrics["metrics"]["sentence_type_distribution"]["counts"]["simple"] >= 0

    failed, text = call(s, "build_baseline", corpus_path=str(good), name="mine")

    assert failed and "at least 25 documents" in text

    big = tmp_path / "big"
    corpus(big, GOOD_LINES, docs=25, words_per_doc=900)
    built = call(s, "build_baseline", corpus_path=str(big), name="mine")[1]

    assert built["documents"] == 25 and built["path"].endswith("baselines/mine.json")

    drift = call(s, "measure_drift", text="However, indeed, moreover. " * 40, baseline="mine")[1]

    assert drift["score"] > 0 and drift["baseline"]["name"] == "mine"
    assert call(s, "measure_drift", text="x", baseline="nope")[0]

    def read(uri):
        return s.call("resources/read", {"uri": uri})["result"]["contents"][0]["text"]

    assert json.loads(read("clarity://baselines")) == ["mine"]
    assert json.loads(read("clarity://baselines/mine"))["documents"] == 25
    assert "subordination_index" in {
        m["name"] for m in json.loads(read("clarity://metrics/schema"))
    }
    assert "requires_all" in read("clarity://schema/composite")
