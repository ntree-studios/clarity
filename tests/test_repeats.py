"""clarity repeats: candidate watchlist YAML from repeated phrases."""

import yaml
from fixtures import SPACER
from test_cli import run

TEXT = (
    "The system has many moving parts. " + SPACER + "Those moving parts break often. "
    + SPACER + "Nobody tracked the moving parts closely."
)


def candidates(*args, text=TEXT):
    code, out, err = run(["repeats", "-", *args], stdin=text)

    return code, out, err


def test_emits_paste_ready_watchlist_yaml_for_a_repeated_phrase():
    code, out, _ = candidates()
    data = yaml.safe_load(out)

    assert code == 0
    assert any(e["term"] == "moving parts" and e["match"] == "phrase" for e in data["watchlist"])


def test_the_yaml_loads_as_a_config_and_then_catches_the_phrase():
    from clarity.config import load_config
    from clarity.engine import analyze

    _, out, _ = candidates()
    found = analyze(TEXT, config=load_config(text=out))["findings"]

    assert any(f["category"] == "watchlist" and f["rule"] == "moving parts" for f in found)


def test_min_occurrences_raises_the_bar():
    _, out, _ = candidates("--min-occurrences", "4")

    assert "moving parts" not in out


def test_since_skips_terms_already_listed_in_a_file(tmp_path):
    known = tmp_path / "clarity.yml"
    known.write_text('watchlist:\n  - {term: "moving parts", max_per_1k: 0, match: phrase}\n')
    _, out, _ = candidates("--since", str(known))

    assert "moving parts" not in out


def test_no_repeats_is_a_clean_empty_result():
    code, out, _ = candidates(text="One short sentence only.")

    assert code == 0
    assert yaml.safe_load(out) in (None, {}, {"watchlist": []}) or "no repeated" in out
