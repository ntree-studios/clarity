"""clarity test, explain and snapshots."""

import json

import pytest
from test_cli import run

from clarity.cli import main


@pytest.fixture
def proj(tmp_path, monkeypatch):
    home, project = tmp_path / "home", tmp_path / "proj"
    (project / ".clarity" / "rules").mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("CLARITY_HOME", str(home))
    monkeypatch.chdir(project)

    return project / ".clarity"


def add_rule(folder, fixtures):
    (folder / "rules" / "mine.yml").write_text(
        "rules:\n  - {id: no-zork, category: hedges, phrases: [zork], match: lower}\n"
    )
    (folder / "rules" / "mine.test.yml").write_text(fixtures)


GOOD = (
    "rule: no-zork\nshould_fire:\n  - \"A zork appeared.\"\n"
    "  - {text: \"The zork left.\", expect: {count: 1, span: \"zork\"}}\n"
    "should_not_fire:\n  - \"Nothing appeared.\"\n  - \"The fork left.\"\n"
)


def test_passing_fixtures_report_counts_and_pass(proj):
    add_rule(proj, GOOD)
    code, out, _ = run(["test", "no-zork"])

    assert code == 0
    assert "no-zork" in out and "2 fire · 2 no-fire" in out and "PASS" in out
    assert "1 passed · 0 failed" in out


def test_a_should_not_fire_match_fails_with_the_matched_text_and_position(proj):
    add_rule(proj, GOOD.replace("The fork left.", "A zork left."))
    code, out, _ = run(["test", "no-zork"])

    assert code == 1 and "FAIL" in out
    assert "should_not_fire case 2 matched" in out
    assert 'matched: "zork"  at 1:3' in out
    assert "Either the fixture" in out


def test_a_should_fire_miss_and_a_wrong_span_expectation_fail(proj):
    broken = GOOD.replace("A zork appeared.", "Nothing here.")
    add_rule(proj, broken.replace('span: \\"zork\\"', 'span: \\"nope\\"'))
    _, out, _ = run(["test", "no-zork"])

    assert "should_fire case 1 failed: the rule did not match" in out


def test_fixture_minimums_are_enforced_at_load(proj):
    add_rule(proj, "rule: no-zork\nshould_fire: [\"A zork.\"]\nshould_not_fire: [\"Nope.\"]\n")
    code, _, err = run(["test"])

    assert code == 2 and "no-zork" in err and "at least 1 and 2" in err


def test_group_target_runs_every_rule_in_a_fixture_file():
    from clarity.config import load_config

    config = load_config(None)
    slug = {n: c.id for n, c in config.categories.items()}
    expected = sum(1 for r in config.rules if slug[int(r.category)] == "self-framing")
    code, out, _ = run(["test", "self-framing"])

    assert code == 0
    assert out.count("PASS") == expected


def test_every_bundled_rule_passes_its_fixtures():
    code, out, _ = run(["test"])

    assert code == 0, out
    assert "0 failed" in out


def test_corpus_mode_flags_a_rule_over_the_ceiling_and_samples_hits(proj, tmp_path):
    add_rule(proj, GOOD)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc-1.md").write_text("A zork here. Another zork there. Plain words follow.\n")
    code, out, _ = run(["test", "--corpus", str(corpus), "--fail-on-regression"])

    assert code == 1
    assert "Corpus: 1 documents" in out and "no-zork" in out and "← high" in out
    assert "Sample hits for no-zork:" in out and "doc-1" in out


def test_against_reports_the_ratio_between_two_corpora(proj, tmp_path):
    add_rule(proj, GOOD)
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    (good / "a.md").write_text("Plain words only here, and some more plain words.\n")
    (bad / "b.md").write_text("A zork and a zork and a zork appeared today.\n")
    _, out, _ = run(["test", "--corpus", str(good), "--against", str(bad)])

    assert "GOOD/1K" in out and "inf" in out and "← strong" in out


def test_snapshot_diff_explains_an_allowance_change_and_exits_clean(proj):
    doc = proj.parent / "draft.md"
    filler = "The team shipped the build on time. " * 200
    doc.write_text("It is genuinely fine and really good. " + filler)
    run(["snapshot", str(doc)])
    (proj / "rules" / "o.yml").write_text("rules:\n  - {id: intensifier, max_per_1k: 90}\n")
    code, out, _ = run(["test", "--snapshots", "--fail-on-regression"])

    assert code == 0
    assert "[allowance raised 1 → 90]" in out
    assert (proj / ".clarity-snapshots" / "draft.json").exists()


def test_snapshot_diff_flags_an_unexplained_change_as_a_regression(proj):
    doc = proj.parent / "draft.md"
    doc.write_text("It is genuinely fine.\n")
    run(["snapshot", str(doc)])
    snap = proj / ".clarity-snapshots" / "draft.json"
    data = json.loads(snap.read_text())
    ghost = {"rule": "intensifier", "category": "intensifiers", "line": 9, "col": 1, "text": "x"}
    data["findings"].append(ghost)
    snap.write_text(json.dumps(data))
    code, out, _ = run(["test", "--snapshots", "--fail-on-regression"])

    assert code == 1 and "[unexplained]" in out


def test_explain_shows_where_a_pattern_breaks_and_where_it_matches():
    _, hit, _ = run(["explain", "framing-noun-phrase", "The honest framing is simple."])
    _, miss, _ = run(["explain", "framing-noun-phrase", "An honest day's work."])

    assert 'MATCH at 1:1 "The honest framing"' in hit
    assert "in lemma set [honest, simple, short, real, ...]" in hit
    assert "NO MATCH · failed at token 3" in miss and "not in lemma set" in miss
    assert main is not None
