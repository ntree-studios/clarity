"""Record sets and YAML query rules over them, in rule files and in profiles."""

from pathlib import Path

import pytest
import yaml
from test_cli import run
from test_config_resolution import dirs, write  # noqa: F401

from clarity import records
from clarity.config import ConfigError, load_config
from clarity.engine import analyze, parse
from clarity.resolve import resolve

HERE = Path(__file__).parent / "topics"
PLANTED = yaml.safe_load((HERE / "planted.yml").read_text(encoding="utf-8"))
SECTIONS = yaml.safe_load((HERE / "sections.yml").read_text(encoding="utf-8"))
SINGLE = "\n\n".join(PLANTED["text"].split("\n\n")[:8])

FINANCE_RULE = """
rules:
  - id: finance-heavy-section
    category: topic-structure
    backend: structural
    function: query
    experimental: true
    message: 'Section "{heading}" is mostly about finance ({named.finance}).'
    params:
      records: topics.sections
      where:
        - {field: named.finance, op: gt, value: 0.5}
      topics:
        named: {finance: mortgage loan interest payment bank, coffee: espresso coffee grind shot}
"""


def findings(text, rule_id, **kw):
    return [f for f in analyze(text, **kw)["findings"] if f["rule"] == rule_id]


def test_default_topic_rules_find_drift_and_digression():
    drift = findings(PLANTED, "topic-drift")
    digression = findings(PLANTED, "topic-digression")

    assert [(f["field"], f["line"]) for f in drift] == [("text", 33)]
    assert "mortgage" in drift[0]["detail"]
    assert [(f["field"], f["line"]) for f in digression] == [("text", 17)]
    assert "4 chunks" in digression[0]["message"]
    assert findings(SINGLE, "topic-drift") == [] and findings(SINGLE, "topic-digression") == []


@pytest.mark.parametrize("text", ["", "One sentence.", "# A title", "Two.\n\nParagraphs."])
def test_topic_rules_stay_silent_on_short_input(text):
    result = analyze(text)

    assert not [f for f in result["findings"] if f["category"] == "topic-structure"]


def test_a_yaml_rule_in_a_rules_file_queries_section_records():
    cfg = load_config(text=FINANCE_RULE)
    hits = findings(SECTIONS, "finance-heavy-section", config=cfg)

    assert [(f["section"], f["field"]) for f in hits] == [("1", "title")]
    assert 'Section "Paying for the house"' in hits[0]["message"]
    assert findings(PLANTED, "finance-heavy-section", config=cfg) == []


def test_aggregate_fires_once_on_word_share():
    cfg = load_config(text="""
rules:
  - id: much-drift
    category: topic-structure
    backend: structural
    function: query
    experimental: true
    message: "Drift is {share} of the words."
    params:
      records: topics.chunks
      where: [{field: kind, op: eq, value: drift}]
      aggregate: {measure: share, op: gt, value: 0.25}
""")
    hits = findings(PLANTED, "much-drift", config=cfg)

    assert len(hits) == 1 and "0.3" in hits[0]["message"]


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ("{records: topics.nope}", "not a record set"),
        ("{records: topics.chunks, where: [{field: colour, op: eq, value: 1}]}", "no field"),
        ("{records: topics.chunks, where: [{field: kind, op: like, value: 1}]}", "op must be"),
        ("{records: topics.chunks, requires: {key: nope, gte: 1}}", "requires"),
        ("{records: topics.chunks, topics: {graph: {k: 0}}}", "topics.graph.k"),
    ],
)
def test_bad_query_params_fail_at_load_with_the_rule_id(params, error):
    text = f"""
rules:
  - {{id: q, category: topic-structure, backend: structural, function: query,
      experimental: true, params: {params}}}
"""
    with pytest.raises(ConfigError, match=error) as exc:
        load_config(text=text)

    assert "rule q" in str(exc.value)


def test_paragraph_and_section_records():
    analysis = parse(SECTIONS, load_config())
    rows, summary = records.fetch(analysis, "paragraphs")

    assert summary["count"] == len(rows) == 15
    assert rows[0]["opener"] == "a" and rows[0]["has_numbers"] is False
    assert rows[8]["has_numbers"] is True  # "twenty percent"
    sections, _ = records.fetch(analysis, "sections")
    assert [s["heading"] for s in sections][1:] == [
        "Pulling the shot", "Paying for the house", "Cleaning the machine",
    ]  # fmt: skip
    cfg = load_config(text="records: {section_kinds: {procedure: [cleaning]}}")
    kinds = [s["kind"] for s in records.fetch(parse(SECTIONS, cfg), "sections")[0]]
    assert kinds[-1] == "procedure"


def test_rule_params_topics_change_settings_for_that_rule_only():
    analysis = parse(PLANTED, load_config())
    base, _ = records.fetch(analysis, "topics.chunks")
    coarse, summary = records.fetch(analysis, "topics.chunks", {"chunk": {"min_words": 50}})

    assert len(coarse) < len(base) and summary["n_chunks"] == len(coarse)


def test_profile_carries_its_own_rule_and_fixtures(dirs):  # noqa: F811
    _, project, sub = dirs
    rule = FINANCE_RULE.replace("rules:\n", "").replace("    experimental: true\n", "")
    write(project / "profiles" / "money.yml", "name: money\nrules:\n" + rule)
    write(project / "profiles" / "money.test.yml", yaml.safe_dump({
        "rule": "finance-heavy-section",
        "should_fire": [{"document": SECTIONS}],
        "should_not_fire": ["One sentence.", "Another short one."],
    }))  # fmt: skip
    path = sub / "doc.yml"
    path.write_text(yaml.safe_dump(SECTIONS))

    assert "finance-heavy-section" in {r.id for r in resolve(None, sub, "money").config.rules}
    assert "finance-heavy-section" not in {r.id for r in resolve(None, sub, "none").config.rules}
    _, out, _ = run(["check", str(path), "--profile", "money", "--format", "json"])
    assert '"rule": "finance-heavy-section"' in out
    _, out, _ = run(["check", str(path), "--profile", "none", "--format", "json"])
    assert "finance-heavy-section" not in out
    code, out, _ = run(["test", "finance-heavy-section", "--profile", "money"])
    assert code == 0 and "PASS" in out


def test_a_profile_rule_without_fixtures_is_refused(dirs):  # noqa: F811
    _, project, sub = dirs
    rule = FINANCE_RULE.replace("rules:\n", "").replace("    experimental: true\n", "")
    write(project / "profiles" / "money.yml", "rules:\n" + rule)

    with pytest.raises(ConfigError, match="finance-heavy-section"):
        resolve(None, sub, "money")


def test_explain_shows_record_fields_and_the_failed_condition():
    code, out, _ = run(["explain", "topic-drift", "-", "--tree"], stdin=yaml.safe_dump(PLANTED))

    assert code == 0
    assert "topics.segments: 4 records" in out
    assert "failed: kind eq drift (has main)" in out


def test_surface_lists_record_sets_and_fields():
    code, out, _ = run(["surface", "--records"])

    assert code == 0
    for name in ("topics.chunks", "topics.segments", "topics.sections", "topics.nodes",
                 "topics.edges", "paragraphs", "sections", "weighted_degree"):  # fmt: skip
        assert name in out
