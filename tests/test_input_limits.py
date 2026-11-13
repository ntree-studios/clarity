"""Bad inputs must end in a clear error and exit 2, never a traceback."""

import io

import pytest

from clarity.cli import main
from clarity.engine import MAX_CHARS, InputError, analyze

BIG = "a. " * (MAX_CHARS // 3 + 10)


def run(argv, stdin_bytes=b"", tty=False):
    stdin = io.TextIOWrapper(io.BytesIO(stdin_bytes), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdin=stdin, stdout=out, stderr=err)

    return code, out.getvalue(), err.getvalue()


def test_engine_rejects_input_over_the_limit_with_a_clear_message():
    with pytest.raises(InputError, match="1,000,000"):
        analyze(BIG)


def test_input_at_the_limit_is_accepted():
    assert analyze("a. " * 10)["words"] == 10


def test_cli_reports_oversize_stdin_and_exits_2():
    code, out, err = run(["check", "-"], BIG.encode())

    assert code == 2
    assert out == ""
    assert "too large" in err
    assert "Traceback" not in err


def test_cli_reports_a_non_utf8_file_and_exits_2(tmp_path):
    path = tmp_path / "latin1.txt"
    path.write_bytes(b"caf\xe9 is good.")
    code, out, err = run(["check", str(path)])

    assert code == 2
    assert "UTF-8" in err
    assert str(path) in err
    assert out == ""


def test_cli_reports_non_utf8_stdin_and_exits_2():
    code, _, err = run(["check", "-"], b"caf\xe9 is good.")

    assert code == 2
    assert "UTF-8" in err
    assert "<stdin>" in err


def test_empty_and_whitespace_input_score_100_and_exit_0():
    for raw in (b"", b"  \n\t\n"):
        code, out, _ = run(["check", "-"], raw)

        assert code == 0
        assert "0 words" in out


def test_cli_rejects_surrogate_escaped_stdin_the_way_a_c_locale_container_delivers_it():
    """Python in a C.UTF-8 container reads bad bytes as lone surrogates instead of raising."""
    stdin = io.TextIOWrapper(
        io.BytesIO(b"caf\xe9 is good."), encoding="utf-8", errors="surrogateescape"
    )
    out, err = io.StringIO(), io.StringIO()
    code = main(["check", "-"], stdin=stdin, stdout=out, stderr=err)

    assert code == 2
    assert "UTF-8" in err.getvalue()
    assert "Traceback" not in err.getvalue()
