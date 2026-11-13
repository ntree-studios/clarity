"""Markdown code, tables, links and HTML are not prose and must not be analyzed as prose."""

from clarity.engine import analyze
from clarity.markdown import mask_markup, prose_paragraphs

FENCE = "```sh\nmake build && docker run -i --rm clarity check - --format json\n```\n"


def rules(text: str) -> set[str]:
    return {f["rule"] for f in analyze(text)["findings"]}


def test_masking_preserves_offsets_and_newlines():
    text = f"Intro text.\n\n{FENCE}\nUse `make build` and see [docs](http://x.io/a) <b>now</b>.\n"
    masked = mask_markup(text)

    assert len(masked) == len(text)
    assert masked.count("\n") == text.count("\n")
    assert "make" not in masked and "x.io" not in masked and "<b>" not in masked
    assert "docs" in masked and "Intro text." in masked


def test_fenced_code_is_not_counted_as_words_or_sentences():
    plain = analyze("We shipped the build on time.\n")
    fenced = analyze("We shipped the build on time.\n\n" + FENCE)

    assert fenced["words"] == plain["words"]
    assert fenced["sentences"] == plain["sentences"]


def test_unclosed_fence_masks_to_the_end():
    assert analyze("Prose here.\n\n```py\nx = 1 and y = 2\n")["words"] == 2


def test_inline_code_tables_and_urls_are_masked():
    text = "Run `make build` now.\n\n| a | b |\n| --- | --- |\n| c | d |\n\nSee https://example.com/x.\n"
    result = analyze(text)

    assert result["words"] == 3  # Run, now, See
    assert "a" not in {f["span"]["text"] for f in result["findings"]}


def test_headings_inside_code_do_not_make_sections():
    result = analyze("Pick tools. It depends.\n\n```sh\n# a shell comment\n```\n")

    assert {d["rule"] for d in result["disabled_rules"]} >= {"it-depends-conclusion"}


def test_prose_next_to_code_is_still_checked():
    text = "It's worth noting that this works.\n\n" + FENCE

    assert "filler-worth-noting" in rules(text)


def test_findings_inside_code_are_not_reported():
    text = "The plan is fine.\n\n```text\nThat said, ultimately, honestly, basically.\n```\n"

    assert not rules(text) & {"filler-transition", "framing-adverbial"}


def test_line_numbers_still_point_at_the_original_text():
    text = f"Intro.\n\n{FENCE}\nHonestly, this is the real answer.\n"
    found = [f for f in analyze(text)["findings"] if f["rule"] == "framing-adverbial"]

    assert found and found[0]["line"] == 7


def test_self_repetition_ignores_symbols_and_numbers():
    first = (
        "Rain fell across the harbor all morning. Crews unloaded crates of oranges and tin. "
        "A gull watched from the old pier. Nobody hurried, because the tide had not turned. "
    )
    second = (
        "Later the foreman counted receipts twice. The kettle in the shed whistled softly. "
        "By noon the clouds had thinned. Children chased pigeons along the quay. "
    )
    junk = "x = 1 ; y = 2. "
    text = junk + first + junk + second + junk

    assert "self-repetition" not in rules(text)


def test_prose_paragraphs_trim_headings_and_skip_lists_and_quotes():
    text = "# Title\nFirst words here.\n\n- item one\n- item two\n\n> quoted\n\nLast words."
    found = [text[a:b] for a, b in prose_paragraphs(text)]

    assert found == ["First words here.", "Last words."]
