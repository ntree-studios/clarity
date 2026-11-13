import io
import json
import re

import pytest

from clarity.cli import main

EM = "—"
CLEAN = "The build passed. The team shipped it on Friday."
DIRTY = f"He left {EM} quickly."


class Stream(io.StringIO):
    def __init__(self, text: str = "", tty: bool = False):
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def run(argv, stdin="", stdin_tty=False, stdout_tty=False):
    out, err = Stream(tty=stdout_tty), Stream()
    code = main(argv, stdin=Stream(stdin, stdin_tty), stdout=out, stderr=err)

    return code, out.getvalue(), err.getvalue()


def test_check_dash_reads_stdin_and_reports_stdin_source():
    code, out, _ = run(["check", "-", "--format", "json"], stdin=DIRTY)
    data = json.loads(out)

    assert {f["source"] for f in data["findings"]} == {"<stdin>"}
    assert any(f["rule"] == "em-dash" for f in data["findings"])
    assert code in (0, 1)


def test_check_without_path_reads_piped_stdin():
    code, out, _ = run(["check", "--format", "json"], stdin=DIRTY, stdin_tty=False)

    assert json.loads(out)["findings"]
    assert code in (0, 1)


def test_check_without_path_and_tty_stdin_is_an_error():
    code, out, err = run(["check"], stdin="", stdin_tty=True)

    assert code == 2
    assert out == ""
    assert "stdin" in err


def test_line_and_col_are_offsets_from_start_of_stream():
    _, out, _ = run(["check", "-", "--format", "json"], stdin=f"First line.\nHe left {EM} fast.")
    dash = next(f for f in json.loads(out)["findings"] if f["rule"] == "em-dash")

    assert (dash["line"], dash["col"]) == (2, 9)


def test_file_path_is_the_source(tmp_path):
    path = tmp_path / "draft.md"
    path.write_text(DIRTY)
    _, out, _ = run(["check", str(path), "--format", "json"])

    assert {f["source"] for f in json.loads(out)["findings"]} == {str(path)}


def test_missing_file_exits_2():
    code, _, err = run(["check", "/no/such/file.md"])

    assert code == 2
    assert "/no/such/file.md" in err


def test_exit_0_when_score_meets_threshold():
    code, _, _ = run(["check", "-", "--fail-under", "100"], stdin=CLEAN)

    assert code == 0


def test_exit_1_when_score_below_threshold():
    code, _, _ = run(["check", "-", "--fail-under", "100"], stdin=DIRTY)

    assert code == 1


def test_score_command_prints_only_the_score_and_uses_the_threshold():
    code, out, _ = run(["score", "-", "--fail-under", "100"], stdin=DIRTY)

    assert code == 1
    assert float(out.strip()) < 100


def test_score_reads_stdin_without_dash():
    code, out, _ = run(["score", "--fail-under", "0"], stdin=CLEAN)

    assert code == 0
    assert float(out.strip()) == 100.0


def test_text_output_has_no_color_when_stdout_is_not_a_tty():
    _, out, _ = run(["check", "-"], stdin=DIRTY, stdout_tty=False)

    assert "\x1b[" not in out


def test_text_output_has_color_on_a_tty():
    _, out, _ = run(["check", "-"], stdin=DIRTY, stdout_tty=True)

    assert "\x1b[" in out


def test_no_color_env_disables_color_on_a_tty(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    _, out, _ = run(["check", "-"], stdin=DIRTY, stdout_tty=True)

    assert "\x1b[" not in out


def test_text_groups_by_category_with_count_header_and_score_summary():
    _, out, _ = run(["check", "-"], stdin=f"{DIRTY} {DIRTY}")

    assert "STRUCTURAL TICS" in out
    assert "2 found \u00b7 0 allowed \u00b7 over by 2" in out
    assert re.search(r"\d+:\d+ +He left", out)
    assert "STYLE SCORE" in out
    assert "READABILITY" in out


def test_confidence_is_visible_and_filterable():
    text = "The architecture wants a single entry point."
    _, out, _ = run(["check", "-"], stdin=text)

    assert "inferred" in out or "\u25d0" in out

    _, out, _ = run(["check", "-", "--format", "json", "--min-confidence", "exact"], stdin=text)

    assert {f["confidence"] for f in json.loads(out)["findings"]} <= {"exact"}


def test_json_shape():
    _, out, _ = run(["check", "-", "--format", "json"], stdin=DIRTY)
    data = json.loads(out)
    finding = data["findings"][0]

    assert {"id", "rule", "category", "severity", "confidence", "message", "source",
            "line", "col", "span", "context", "over_allowance"} <= set(finding)
    assert {"id", "name", "found", "max_per_1k", "over_by", "rate_per_1k", "penalty",
            "capped"} <= set(data["categories"][0])
    assert {"score", "readability"} <= set(data)


def test_accept_suppresses_the_finding_even_when_lines_move(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, out, _ = run(["check", "-", "--format", "json"], stdin=DIRTY)
    fid = next(f["id"] for f in json.loads(out)["findings"] if f["rule"] == "em-dash")

    code, _, _ = run(["accept", fid])

    assert code == 0
    assert (tmp_path / ".clarity-accept").read_text().split() == [fid]

    moved = "A new first paragraph.\n\n" + DIRTY
    _, out, _ = run(["check", "-", "--format", "json"], stdin=moved)

    assert not [f for f in json.loads(out)["findings"] if f["rule"] == "em-dash"]


def test_accept_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(["accept", "abc123"])
    run(["accept", "abc123"])

    assert (tmp_path / ".clarity-accept").read_text().split() == ["abc123"]


def test_rules_lists_every_rule_and_filters_by_category():
    _, out, _ = run(["rules"])

    assert "em-dash" in out and "intensifier" in out

    _, out, _ = run(["rules", "--category", "4"])

    assert "intensifier" in out and "em-dash" not in out


def test_rules_unknown_category_exits_2():
    code, _, err = run(["rules", "--category", "99"])

    assert code == 2
    assert "99" in err


def test_bad_config_exits_2(tmp_path):
    cfg = tmp_path / "clarity.yml"
    cfg.write_text("rules:\n  - {id: x, category: 1, scope: nonsense}\n")
    code, _, err = run(["check", "-", "--config", str(cfg)], stdin=CLEAN)

    assert code == 2
    assert "scope" in err


@pytest.mark.parametrize(("fail_outside", "expected"), [(True, 1), (False, 0)])
def test_fail_outside_band_controls_exit_code_independent_of_style_score(
    tmp_path, fail_outside, expected
):
    cfg = tmp_path / "clarity.yml"
    flag = str(fail_outside).lower()
    cfg.write_text(f"readability: {{target_grade: [30, 40], fail_outside_band: {flag}}}\n")
    code, _, _ = run(["check", "-", "--config", str(cfg), "--fail-under", "0"], stdin=CLEAN)

    assert code == expected
