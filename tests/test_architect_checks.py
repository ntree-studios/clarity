"""Places a spec like this one most likely breaks: each is a check on a known weak point."""

import yaml

from clarity.accept import accept
from clarity.clauses import clauses, is_clause_head
from clarity.config import load_config
from clarity.engine import analyze
from clarity.nlp import get_nlp

# Clause counts follow spaCy's parse: the small model sometimes reads a verb as a noun ("runs" in
# "while the build runs"), and that clause is then not counted. So the test checks the invariants
# (no overlap, no double count, one clause per finite head) and not a hand-counted number.
COMPOUND_COMPLEX = (
    "We ship on Friday because the tests pass, and the team, which wrote them, waits. "
    "If it fails, we stop."
)


def cfg(*rules):
    return load_config(text=yaml.safe_dump({"rules": list(rules)}))


def test_clauses_partition_each_sentence_with_no_overlap_or_double_count():
    doc = get_nlp()(COMPOUND_COMPLEX)
    owner: dict[int, int] = {}

    for clause in clauses(doc):
        for tok in clause.tokens:
            assert tok.i not in owner, f"{tok.text!r} belongs to two clauses"
            owner[tok.i] = clause.head.i

    words = {t.i for t in doc if not t.is_space}

    assert set(owner) == words
    assert len({c.head.i for c in clauses(doc)}) == len(clauses(doc))

    for sent in doc.sents:
        heads = {t.i for t in sent if is_clause_head(t)} | {sent.root.i}
        found = {c.head.i for c in clauses(doc) if c.head.sent == sent}

        assert found == heads


def test_fractional_allowance_never_rounds_up():
    rule = {"id": "intensifier", "max_per_1k": 0.5}
    filler = "The team shipped the build on time. " * 60  # 487 words with the two below
    text = "It is genuinely good. " + filler + "It is truly fine."
    words = analyze(text)["words"]
    flags = [f["over_allowance"] for f in analyze(text, config=cfg(rule))["findings"]
             if f["rule"] == "intensifier"]  # fmt: skip

    assert int(0.5 * words / 1000) == 0 and words < 2000
    assert flags == [True, True]

    long = text + " The team shipped the build on time." * 400
    flags = [f["over_allowance"] for f in analyze(long, config=cfg(rule))["findings"]
             if f["rule"] == "intensifier"]  # fmt: skip

    assert analyze(long)["words"] >= 2000 and flags == [False, True]


def test_a_suppressed_match_does_not_consume_allowance():
    rule = {"id": "intensifier", "max_per_1k": 1000,
            "suppress_if": [{"near": {"lemma": "fine", "within": 2}}]}  # fmt: skip
    text = "It is truly fine. It is genuinely good."
    one = analyze(text, config=cfg(rule))
    kept = [f for f in one["findings"] if f["rule"] == "intensifier"]
    strict = analyze(text, config=cfg({**rule, "max_per_1k": 0}))
    over = [f for f in strict["findings"] if f["rule"] == "intensifier"]

    assert [f["span"]["text"] for f in kept] == ["genuinely"]
    assert [f["span"]["text"] for f in over] == ["genuinely"]
    assert next(c for c in one["categories"] if c["id"] == "intensifiers")["found"] == 1


RESTATE = {"id": "sentence-restatement", "category": "redundancy", "backend": "structural",
           "function": "sentence_restatement", "max_per_1k": 0,
           "params": {"jaccard": 0.5, "idf_weighted": True, "require_shorter_second": True,
                      "window": 2}}  # fmt: skip


def test_idf_on_two_paragraphs_neither_fires_on_everything_nor_nothing():
    restated = (
        "The loader reads every rule from the project folder. The loader reads every project rule."
    )
    other = "Rain fell across the harbor. Crews unloaded crates of oranges."
    topical = "Docker gives you a reproducible image. The image ships with the spaCy model."

    def fired(text):
        return [f for f in analyze(text, config=cfg(RESTATE))["findings"]
                if f["rule"] == "sentence-restatement"]  # fmt: skip

    assert len(fired(f"{restated}\n\n{other}")) == 1
    assert fired(f"{topical}\n\n{other}") == []
    assert len(fired(f"{other}\n\n{restated}")) == 1


def test_a_sentence_composite_needs_both_members_in_the_same_sentence():
    combo = {"id": "combo", "category": "composite", "backend": "composite",
             "count_scope": "sentence", "max_per_scope": 0,
             "requires_all": [{"rule": "hedge"}, {"rule": "intensifier"}]}  # fmt: skip
    far = "This is arguably fine. We said so. It is genuinely good."

    def combos(text):
        return [f for f in analyze(text, config=cfg(combo))["findings"] if f["rule"] == "combo"]

    assert combos(far) == []
    assert len(combos("This is arguably genuinely fine. We said so.")) == 1


def test_an_exemption_survives_edits_elsewhere_in_the_document(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLARITY_HOME", str(tmp_path / "home"))
    target = "The tool is genuinely useful for teams."
    first = [f for f in analyze(target)["findings"] if f["rule"] == "intensifier"]
    accept(first[0]["id"][:6])
    from clarity.accept import load_accepted

    edited = (
        "A new opening paragraph.\n\nIt has several sentences. They push the line numbers down.\n\n"
    )
    after = analyze(edited + target, accepted=load_accepted())

    assert not [f for f in after["findings"] if f["rule"] == "intensifier"]
    assert [f["line"] for f in analyze(edited + target)["findings"] if f["rule"] == "intensifier"][
        0
    ] > 1
