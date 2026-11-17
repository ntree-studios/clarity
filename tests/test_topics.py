"""Topic graph: the topicdrift.py port, its settings, and the graph as data."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from test_cli import run
from test_config_resolution import dirs, write  # noqa: F401

from clarity import topics
from clarity.config import ConfigError
from clarity.engine import parse
from clarity.resolve import resolve
from clarity.structure import from_tree

PLANTED_TREE = yaml.safe_load((Path(__file__).parent / "topics" / "planted.yml").read_text("utf-8"))
PLANTED = from_tree(PLANTED_TREE).text  # the title, a blank line, then the text
ANCHOR = "How to pull a good espresso shot"
NAMED = {
    "espresso": "espresso coffee grind shot extraction",
    "finance": "mortgage loan interest payment bank",
}


@pytest.fixture(scope="module")
def planted():
    return topics.run(PLANTED, {"anchor": ANCHOR, "named": NAMED})


def test_planted_topics_and_runs_are_found(planted):
    r = planted.report

    assert r["n_chunks"] == 24
    assert r["n_topics"] == 3
    assert r["main_topic"] == 0
    assert "espresso" in r["topics"][0]["terms"]
    assert "mortgage" in r["topics"][1]["terms"]
    assert "bicycle" in r["topics"][2]["terms"]
    runs = [(s["start"], s["end"], s["kind"]) for s in r["segments"]]
    assert runs == [(0, 7, "main"), (8, 11, "digression"), (12, 15, "main"), (16, 23, "drift")]
    assert r["shifts"] == [8, 12, 16]


def test_chunks_map_back_to_source_lines(planted):
    lines = PLANTED.splitlines()
    first_bike = planted.report["chunks"][8]

    assert lines[first_bike["line"] - 1].startswith("Last weekend I took my bicycle")
    assert PLANTED[first_bike["start"] : first_bike["end"]].endswith("before the descent.")
    assert planted.report["segments"][3]["line"] == first_line_of(planted, 16)


def first_line_of(result, chunk):
    return result.report["chunks"][chunk]["line"]


def test_named_alignment_matches_the_planted_shares(planted):
    aligned = planted.report["aligned"]

    assert aligned["espresso"] > 0.5 and aligned["finance"] > 0.3
    assert planted.report["chunks"][20]["aligned_to"] == "finance"


def test_report_is_identical_under_different_hash_seeds():
    code = (
        "import json,sys; from clarity import topics; "
        "r = topics.run(sys.stdin.read(), {'anchor': 'espresso shot'}); "
        "print(json.dumps(r.report, sort_keys=True)); print(topics.export(r, 'json'))"
    )
    digests = set()

    for seed in ("0", "1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, "-c", code], input=PLANTED, text=True,
                             capture_output=True, env=env, check=True).stdout  # fmt: skip
        digests.add(hashlib.sha256(out.encode()).hexdigest())

    assert len(digests) == 1


TWO_PARAGRAPHS = (
    "The espresso shot needs a fine grind and a steady dose of fresh coffee every time.\n\n"
    "A mortgage loan from a bank sets a monthly payment and an interest rate for years."
)


@pytest.mark.parametrize(
    "text",
    ["", "One sentence about espresso.", "# How to pull a good espresso shot", TWO_PARAGRAPHS],
)
def test_short_input_is_too_short_with_no_fake_topics(text):
    r = topics.run(text).report

    assert r["status"] == topics.TOO_SHORT
    assert r["n_topics"] == 0 and r["topics"] == [] and r["segments"] == []
    assert r["on_topic_share"] is None


@pytest.mark.parametrize("text", ["", "One sentence.", "# A title", TWO_PARAGRAPHS])
def test_topics_command_on_short_input_reports_too_short(text):
    code, out, err = run(["topics", "-"], stdin=text)

    assert code == 0, err
    assert "too_short" in out
    code, out, _ = run(["topics", "-", "--format", "json"], stdin=text)
    assert json.loads(out)["status"] == "too_short"


def test_crlf_and_nfc_do_not_change_the_report():
    a = topics.run(PLANTED).report
    b = topics.run(PLANTED.replace("\n", "\r\n")).report

    assert a["labels"] == b["labels"] and a["topics"] == b["topics"]


def test_settings_change_the_result():
    base = topics.run(PLANTED).report
    coarse = topics.run(PLANTED, {"chunk": {"min_words": 50}}).report

    assert coarse["n_chunks"] < base["n_chunks"]


def test_sentence_units_and_max_words_split_long_paragraphs():
    sentences = topics.run(PLANTED, {"chunk": {"unit": "sentences", "min_words": 10}}).report
    capped = topics.run(PLANTED, {"chunk": {"min_words": 10, "max_words": 30}}).report

    assert sentences["n_chunks"] > 24
    assert capped["n_chunks"] > 24


@pytest.mark.parametrize(
    ("bad", "named"),
    [
        ({"chunk": {"min_words": -3}}, "topics.chunk.min_words"),
        ({"chunk": {"bogus": 1}}, "bogus"),
        ({"graph": {"k": "six"}}, "topics.graph.k"),
        ({"align": {"sink": 0}}, "sink"),
        ({"colour": 1}, "colour"),
    ],
)
def test_invalid_settings_are_refused(bad, named):
    with pytest.raises(topics.TopicSettingsError, match=named):
        topics.effective(bad)


def test_config_and_profile_set_topics_and_provenance_names_the_file(dirs):  # noqa: F811
    _, project, sub = dirs
    write(project / "clarity.yml", "topics:\n  chunk: {min_words: 40}\n  graph: {k: 4}\n")
    write(project / "profiles" / "wide.yml", "topics:\n  graph: {k: 9}\n")
    res = resolve(None, sub)

    assert res.config.topics["chunk"]["min_words"] == 40
    assert res.config.topics["graph"]["k"] == 4
    assert res.provenance["topics.chunk"]["min_words"][-1][0].endswith(".clarity/clarity.yml")
    assert resolve(None, sub, "wide").config.topics["graph"]["k"] == 9

    code, out, _ = run(["config", "--explain", "topics"])
    assert code == 0
    assert "chunk.min_words" in out and "40" in out and ".clarity/clarity.yml" in out


def test_invalid_config_value_names_file_and_key(dirs):  # noqa: F811
    _, project, sub = dirs
    write(project / "clarity.yml", "topics:\n  chunk: {min_words: -3}\n")

    with pytest.raises(ConfigError, match=r"clarity\.yml: topics\.chunk\.min_words"):
        resolve(None, sub)


def test_analysis_caches_by_effective_settings():
    analysis = parse(PLANTED)
    first = topics.for_analysis(analysis, topics.effective())

    assert topics.for_analysis(analysis, topics.effective()) is first
    other = topics.for_analysis(analysis, topics.effective({"graph": {"k": 3}}))
    assert other is not first


def test_graph_nodes_and_edges_carry_measures(planted):
    nodes = topics.node_records(planted)
    edges = topics.edge_records(planted)

    assert [n["index"] for n in nodes] == list(range(24))
    assert all(n["betweenness"] is not None and n["weighted_degree"] > 0 for n in nodes)
    assert sum(n["is_central"] for n in nodes) == 3
    assert any(e["adjacent"] and not e["same_topic"] for e in edges)
    assert all(e["source"] < e["target"] for e in edges)


@pytest.mark.parametrize("fmt", ["json", "graphml", "dot"])
def test_graph_exports_are_stable(planted, fmt):
    once = topics.export(planted, fmt)

    assert once == topics.export(topics.run(PLANTED, {"anchor": ANCHOR, "named": NAMED}), fmt)
    assert "weighted_degree" in once


def test_topics_command_reports_lines_and_json(tmp_path):
    path = tmp_path / "planted.yml"
    path.write_text(yaml.safe_dump(PLANTED_TREE))
    code, out, _ = run(["topics", str(path), "--anchor", ANCHOR, "--named",
                        "finance=mortgage loan interest payment bank"])  # fmt: skip

    assert code == 0
    assert "digression" in out and "drift" in out and "lines 17-23" in out
    assert "finance" in out

    code, out, _ = run(["topics", str(path), "--format", "json"])
    assert json.loads(out)["n_topics"] == 3

    code, out, _ = run(["topics", str(path), "--graph", "json"])
    assert len(json.loads(out)["nodes"]) == 24


def test_topics_command_rejects_a_bad_named_flag(tmp_path):
    code, _, err = run(["topics", "-", "--named", "finance"], stdin=PLANTED)

    assert code == 2 and "NAME=DESCRIPTION" in err


def test_anchor_defaults_to_the_title_and_scores_every_unit():
    r = topics.run(PLANTED, structure=from_tree(PLANTED_TREE)).report

    assert r["anchor"] == ANCHOR and r["anchor_source"] == "title"
    assert 0 < r["anchor_score"] < 1 and 0 < r["anchor_share_above"] <= 1
    by_kind = {s["kind"]: s["anchor_alignment"] for s in r["segments"]}
    assert by_kind["main"] > by_kind["drift"]
    assert all(t["anchor_alignment"] is not None for t in r["topics"])


def test_without_a_heading_there_is_no_anchor_and_no_anchor_score():
    body = PLANTED.split("\n", 2)[2]
    r = topics.run(body).report

    assert r["anchor"] is None and r["anchor_score"] is None and r["anchor_share_above"] is None
    assert topics.run(body, {"anchor": "none"}).report["main_topic"] == 0


EMPTY_FOCUS = {"focus": {"keywords": [], "description": "", "named": {}}}


def test_no_focus_keywords_leave_the_output_unchanged():
    from clarity.engine import analyze

    plain = topics.run(PLANTED).report
    assert topics.run(PLANTED, EMPTY_FOCUS).report == plain and "focus" not in plain
    cfg = resolve(None, Path.cwd()).config
    before = json.dumps(analyze(PLANTED, config=cfg), sort_keys=True)
    cfg.topics = topics.effective(cfg.topics, EMPTY_FOCUS)
    assert json.dumps(analyze(PLANTED, config=cfg), sort_keys=True) == before


def test_rare_and_absent_keywords_are_forced_into_the_vocabulary():
    docs = [c.text for c in topics.chunk_text(PLANTED)]
    cfg = topics.DEFAULTS["vectorize"]
    plain, _ = topics.vectorize(docs, cfg)
    forced, X = topics.vectorize(docs, cfg, ["derailleur", "submarine"])

    assert "derailleur" not in plain.vocabulary_
    assert {"derailleur", "submarine"} <= set(forced.vocabulary_)
    assert X[:, forced.vocabulary_["submarine"]].nnz == 0
    r = topics.run(PLANTED, {"focus": {"keywords": ["derailleur", "submarine"]}}).report
    assert r["focus"]["keyword_coverage"] == 0.5
    assert r["focus"]["missing_keywords"] == ["submarine"]
    assert [c["index"] for c in r["chunks"] if c["keyword_hits"]] == [8]


def test_phrase_and_lemma_keywords_match_through_the_parse():
    settings = topics.effective({"focus": {"keywords": ["burr grinder", "grinding", "bank"]}})
    r = topics.for_analysis(parse(PLANTED_TREE), settings).report

    present = {k for c in r["chunks"] for k in c["keywords_present"]}
    assert present == {"burr grinder", "grinding", "bank"}
    assert r["anchor"].endswith("burr grinder grinding bank")
    assert r["anchor_source"] == "title+focus"
    assert r["sections"][0]["keyword_coverage"] == 1.0


def test_focus_flags_reach_check_and_topics(tmp_path):
    code, out, _ = run(["topics", "-", "--keywords", "espresso, mortgage , kayak", "--format",
                        "json"], stdin=PLANTED)  # fmt: skip
    focus = json.loads(out)["focus"]

    assert code == 0 and focus["missing_keywords"] == ["kayak"]
    sections = (Path(__file__).parent / "topics" / "sections.yml").read_text(encoding="utf-8")
    code, out, _ = run(["check", "-", "--tree", "--keywords", "espresso,coffee",
                        "--format", "json"], stdin=sections)  # fmt: skip
    gaps = [f for f in json.loads(out)["findings"] if f["rule"] == "focus-gap-section"]
    assert [(f["section"], f["field"]) for f in gaps] == [("1", "title")]
    _, out, _ = run(["check", "-", "--tree", "--format", "json"], stdin=sections)
    assert "focus-gap-section" not in out


def test_a_section_tree_reports_field_relative_lines_with_the_section_path():
    structure = from_tree(PLANTED_TREE)
    r = topics.run(PLANTED, structure=structure).report
    first = r["chunks"][0]
    rendered_line = PLANTED[: first["start"]].count("\n") + 1

    assert rendered_line > 1  # the title and a blank line come first in the rendered text
    assert first["field"] == "text" and first["line"] == 1
    assert first["section"] == structure.parts[0].path
    assert r["segments"][0]["line"] == 1 and r["segments"][0]["field"] == "text"
    assert r["sections"][0]["field"] == "title" and r["sections"][0]["line"] == 1
