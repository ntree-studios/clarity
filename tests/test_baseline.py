"""Baselines, drift, the drift gate and trend."""

import json

import pytest
from test_bootstrap import GOOD_LINES, corpus
from test_cli import run

WORDS = 900


@pytest.fixture(scope="module")
def base_corpus(tmp_path_factory):
    folder = tmp_path_factory.mktemp("base") / "docs"
    corpus(folder, GOOD_LINES, docs=25, words_per_doc=WORDS)

    return folder


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setenv("CLARITY_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    return tmp_path


def test_a_baseline_under_the_floor_is_refused_with_the_reason(work, tmp_path):
    corpus(tmp_path / "thin", GOOD_LINES, docs=3, words_per_doc=100)
    code, _, err = run(["baseline", "build", str(tmp_path / "thin")])

    assert code == 2 and "at least 25 documents" in err
    assert not (work / ".clarity" / "baselines").exists()


def test_build_list_show_and_drift_against_a_baseline(work, base_corpus):
    code, out, _ = run(["baseline", "build", str(base_corpus), "--name", "mine"])
    stored = json.loads((work / ".clarity" / "baselines" / "mine.json").read_text())

    assert code == 0 and "25 documents" in out
    assert stored["documents"] == 25 and "subordination_index" in stored["metrics"]
    assert run(["baseline", "list"])[1].split() == ["mine"]
    assert "subordination_index" in run(["baseline", "show", "mine"])[1]

    odd = "However, indeed, moreover, it is what it is. " * 30
    _, report, _ = run(["drift", "-", "--baseline", "mine", "--format", "json"], stdin=odd)
    data = json.loads(report)

    assert data["most_divergent"] and data["score"] > 0
    assert data["baseline"]["documents"] == 25

    text = run(["drift", "-", "--baseline", "mine"], stdin=odd)[1]

    assert "MOST DIVERGENT" in text and "not a verdict" in text


def test_drift_gate_changes_the_exit_code_only_when_asked(work, base_corpus):
    run(["baseline", "build", str(base_corpus), "--name", "mine"])
    odd = "However, indeed, moreover, it is what it is. " * 30
    args = ["check", "-", "--fail-under", "0", "--drift-baseline", "mine"]

    assert run(args, stdin=odd)[0] == 0
    assert run([*args, "--max-drift", "0.1"], stdin=odd)[0] == 1
    score = json.loads(run(["drift", "-", "--baseline", "mine", "--format", "json"], stdin=odd)[1])
    above = str(score["score"] + 1)

    assert run([*args, "--max-drift", above], stdin=odd)[0] == 0
    assert "DRIFT" in run(args, stdin=odd)[1]
    assert run(["check", "-", "--max-drift", "1"], stdin=odd)[0] == 2
    assert run(["drift", "-", "--baseline", "nope"], stdin="x")[0] == 2


def test_trend_reads_snapshot_history_and_marks_the_habit_within_allowance(work):
    draft = work / "draft.md"
    draft.write_text("We leverage robust tools to empower teams. Rain fell on the harbor.")
    run(["snapshot", "draft.md"])
    draft.write_text("Rain fell on the harbor.")
    code, out, _ = run(["trend", "draft.md", "--rule", "corporate-tier-a"])
    rows = out.splitlines()

    assert code == 0 and len(rows) == 2
    assert "3 hits" in rows[0] and "0 hits" in rows[1] and "within allowance" in rows[1]
    assert "score" in run(["trend", "draft.md"])[1]
    assert run(["trend", "draft.md", "--rule", "nope"])[0] == 2
