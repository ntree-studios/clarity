"""clarity command line."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, TextIO

from clarity.accept import accept, load_accepted
from clarity.config import ConfigError, describe_rules, load_config
from clarity.engine import SOURCE_STDIN, analyze
from clarity.nlp import ModelError
from clarity.render import render_json, render_text

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


class CliError(Exception):
    """A user-facing error that maps to exit code 2."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clarity", description="Prose linter for AI-slop tics.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, helptext in (("check", "report findings"), ("score", "print the score only")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("path", nargs="?", help="file, or - for stdin")
        p.add_argument("--config", help="clarity.yml with overrides")
        p.add_argument("--fail-under", type=float, default=80.0)
        p.add_argument("--min-confidence", choices=["exact", "inferred"], default="inferred")

        if name == "check":
            p.add_argument("--format", choices=["text", "json"], default="text")

    acc = sub.add_parser("accept", help="exempt a finding by id")
    acc.add_argument("finding_id")

    rules = sub.add_parser("rules", help="list active rules")
    rules.add_argument("--category", type=int)
    rules.add_argument("--config")

    sub.add_parser("mcp", help="serve MCP over stdio")

    return parser


def _read_source(path: str | None, stdin: TextIO) -> tuple[str, str]:
    """Return (text, source label). Stdin when path is - or absent and stdin is piped."""
    if path == "-" or (path is None and not stdin.isatty()):
        return stdin.read(), SOURCE_STDIN

    if path is None:
        raise CliError("no path given and stdin is a terminal; pass a file or pipe text in")

    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), path
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror}") from exc


def _use_color(stream: TextIO) -> bool:
    return stream.isatty() and "NO_COLOR" not in os.environ


def _analyze(args: argparse.Namespace, stdin: TextIO) -> tuple[dict[str, Any], str]:
    text, source = _read_source(args.path, stdin)
    config = load_config(args.config)
    result = analyze(
        text,
        source=source,
        config=config,
        min_confidence=args.min_confidence,
        accepted=load_accepted(),
    )

    return result, source


def _exit_code(result: dict[str, Any], fail_under: float) -> int:
    band = result["readability"]

    if result["score"] < fail_under:
        return EXIT_FAIL

    if band["fail_outside_band"] and not band["inside_band"]:
        return EXIT_FAIL

    return EXIT_OK


def _cmd_rules(args: argparse.Namespace, stdout: TextIO) -> int:
    config = load_config(args.config)

    if args.category is not None and args.category not in config.categories:
        raise CliError(f"unknown category {args.category}")

    for row in describe_rules(config, args.category):
        stdout.write(
            f"{row['category_number']:>2} {row['category']:<14} {row['id']:<32} "
            f"{row['severity']:<8} {row['confidence']:<9} max_per_1k={row['max_per_1k']:g}\n"
        )

    return EXIT_OK


def main(
    argv: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    args = _parser().parse_args(argv)

    try:
        if args.command == "mcp":
            from clarity.mcp_server import serve

            serve()

            return EXIT_OK

        if args.command == "accept":
            added = accept(args.finding_id)
            stdout.write(("accepted " if added else "already accepted ") + args.finding_id + "\n")

            return EXIT_OK

        if args.command == "rules":
            return _cmd_rules(args, stdout)

        result, source = _analyze(args, stdin)
    except (CliError, ConfigError, ModelError) as exc:
        stderr.write(f"clarity: {exc}\n")

        return EXIT_ERROR

    if args.command == "score":
        stdout.write(f"{result['score']:g}\n")
    elif args.format == "json":
        stdout.write(render_json(result, source) + "\n")
    else:
        stdout.write(render_text(result, source, _use_color(stdout)) + "\n")

    return _exit_code(result, args.fail_under)


if __name__ == "__main__":
    sys.exit(main())
