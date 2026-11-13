"""The text report layout."""

import re

from test_cli import run

EM = "—"
FILLER = "The team shipped the build on time. "
SAMPLE = (
    "# Notes\n\n"
    f"It's worth noting that this is genuinely a robust platform. He left {EM} quickly.\n"
    "The architecture wants a single entry point.\n"
)
ROW = re.compile(r"^  [●◐○]  \d+:\d+ +\S.*\[[0-9a-f]{6}\]$")
HEADER = re.compile(r"^[A-Z][A-Z \-]+ {2,}\d+ found · \d+ allowed · (over by \d+|ok)$")


def report(text: str = SAMPLE, *args: str) -> list[str]:
    _, out, _ = run(["check", "-", *args], stdin=text)

    return out.splitlines()


def test_first_line_names_the_source_words_and_sentences():
    first = report()[0]

    assert re.match(r"^<stdin> {3}\d+ words · \d+ sentences$", first)


def test_categories_have_uppercase_headers_with_found_allowed_and_over_by():
    headers = [line for line in report() if HEADER.match(line)]

    assert headers
    assert any(h.startswith("FILLER TRANSITIONS") for h in headers)
    assert any(h.startswith("STRUCTURAL TICS") for h in headers)


def test_header_counts_line_up_in_one_column():
    columns = {line.index(" ", 1) for line in report() if HEADER.match(line)}
    starts = {re.search(r"\d+ found", line).start() for line in report() if HEADER.match(line)}

    assert len(starts) == 1
    assert columns


def test_every_finding_is_a_marker_row_with_position_snippet_and_short_id():
    rows = [line for line in report() if re.match(r"^  [●◐○] ", line)]

    assert rows
    assert all(ROW.match(r) for r in rows), rows


def test_markers_distinguish_exact_inferred_and_within_allowance():
    out = "\n".join(report())

    assert "●" in out  # exact, over allowance
    assert "◐" in out  # inferred, over allowance


def test_a_finding_within_the_allowance_is_marked_hollow_and_the_header_says_ok():
    text = "It is genuinely good. " + FILLER * 150
    lines = report(text)
    header = next(line for line in lines if line.startswith("INTENSIFIERS"))
    row = next(line for line in lines if "genuinely" in line and ROW.match(line))

    assert header.endswith("1 found · 1 allowed · ok")
    assert row.lstrip().startswith("○")


def test_inferred_findings_carry_a_detail_line():
    lines = report()
    i = next(n for n, line in enumerate(lines) if "false-agency" in line and ROW.match(line))

    assert lines[i + 1].startswith("            ")
    assert lines[i + 1].strip()


def test_score_block_shows_score_and_pass_or_fail_against_the_threshold():
    fail = "\n".join(report(SAMPLE, "--fail-under", "100"))
    ok = "\n".join(report(SAMPLE, "--fail-under", "0"))

    assert re.search(r"STYLE SCORE +\d+(\.\d+)? / 100 +FAIL \(--fail-under 100\)", fail)
    assert re.search(r"STYLE SCORE +\d+(\.\d+)? / 100 +PASS \(--fail-under 0\)", ok)


def test_score_block_lists_per_category_penalty_rate_and_allowance():
    lines = report()
    pattern = re.compile(r"^  [a-z ]+ +-\d+(\.\d+)? +\d+(\.\d+)?/1k +allowed \d+")
    rows = [line for line in lines if pattern.search(line)]

    assert rows
    assert any("structural tics" in r for r in rows)


def test_readability_table_has_all_six_metrics_and_flags_the_band(tmp_path):
    cfg = tmp_path / "clarity.yml"
    cfg.write_text("readability: {target_grade: [1, 2]}\n")
    out = "\n".join(report(SAMPLE, "--config", str(cfg)))

    for name in (
        "Flesch Reading Ease",
        "Flesch-Kincaid Grade",
        "Gunning Fog",
        "SMOG",
        "Coleman-Liau",
        "Automated Readability",
    ):
        assert name in out

    assert "READABILITY" in out and "target grade 1-2" in out
    assert re.search(r"Flesch-Kincaid Grade +[\d.\-]+ +← (above|below) band", out)
    assert re.search(r"Flesch Reading Ease +[\d.\-]+ +\(", out)


def test_footer_counts_findings_and_prints_the_filter_and_accept_hints():
    out = "\n".join(report())

    assert re.search(r"\d+ findings · \d+ over allowance · \d+ within", out)
    assert re.search(r"● exact \(\d+\) +◐ inferred \(\d+\) +○ within allowance \(\d+\)", out)
    assert "Filter to exact only:  clarity check --min-confidence exact" in out
    assert re.search(r"Accept a finding: +clarity accept [0-9a-f]{6}\b", out)


def test_accept_takes_the_short_id_shown_in_the_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = "\n".join(report())
    short = re.search(r"clarity accept ([0-9a-f]{6})", out).group(1)
    row = next(line for line in out.splitlines() if f"[{short}]" in line)

    run(["accept", short])
    again = "\n".join(report())

    assert f"[{short}]" not in again
    assert row.strip() != ""


def test_plain_text_prints_a_notice_naming_the_inert_section_rules():
    out = "\n".join(report("Pick tools. It depends."))

    assert re.search(r"notice: .*section-restatement.*it-depends-conclusion", out)
    assert "no markdown headings" in out


def test_headings_remove_the_notice():
    assert "notice:" not in "\n".join(report("# Choice\n\nPick tools carefully. It depends."))


def test_json_reports_disabled_rules_with_a_reason():
    import json

    _, out, _ = run(["check", "-", "--format", "json"], stdin="Pick tools. It depends.")
    data = json.loads(out)

    assert {d["rule"] for d in data["disabled_rules"]} >= {"it-depends-conclusion"}
    assert all(d["reason"] for d in data["disabled_rules"])



def test_a_wide_line_and_column_still_leave_a_gap_before_the_snippet():
    text = "\n" * 150 + " " * 100 + "It is genuinely a robust platform.\n"
    rows = [line for line in report(text) if re.match(r"^  [●◐○]  ", line)]

    assert rows
    assert all(re.match(r"^  [●◐○]  \d+:\d+ +\S", line) for line in rows)
