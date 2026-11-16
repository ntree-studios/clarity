"""The off-topic rules on the planted set: each finds most planted cases with few false alarms."""

from planted_topics import OFF_TOPIC_RULES, build, score

from clarity.engine import analyze


def test_off_topic_rules_on_the_planted_set():
    table = score(build(), lambda tree: analyze(tree)["findings"])

    for rule in OFF_TOPIC_RULES:
        row = table[rule]
        assert row["planted"] == 4
        assert row["found"] >= 3, (rule, row)
        assert row["false_alarms"] <= 2, (rule, row)


def test_on_topic_documents_raise_no_off_topic_finding():
    for case in build():
        if case.name.endswith("on-topic"):
            hits = [f for f in analyze(case.tree)["findings"] if f["rule"] in OFF_TOPIC_RULES]
            assert hits == [], case.name


def test_off_subject_columns_are_flagged_and_their_siblings_are_not():
    """3 of 4 planted off-subject columns, no false alarms. The insulation deck's mortgage column
    shares cost and house words with its siblings (similarity 0.106), so it is missed."""
    from planted_topics import build_trees

    found = false_alarms = 0

    for _, tree, off in build_trees():
        found_ = analyze(tree)["findings"]
        hits = [f["section"] for f in found_ if f["rule"] == "section-off-parent"]
        found += off in hits
        false_alarms += len([h for h in hits if h != off])

    assert (found, false_alarms) == (3, 0)


def test_section_trees_skip_drift_and_digression():
    from planted_topics import build_trees

    for name, tree, _ in build_trees():
        rules = {f["rule"] for f in analyze(tree)["findings"]}

        assert not rules & {"topic-drift", "topic-digression", "off-topic-share"}, name
