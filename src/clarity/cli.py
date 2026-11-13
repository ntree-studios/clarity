"""clarity command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from clarity import baseline, config_cmds, harness, surface
from clarity.accept import accept, load_accepted
from clarity.config import ConfigError, describe_rules
from clarity.engine import SOURCE_STDIN, InputError, analyze
from clarity.nlp import ModelError
from clarity.render import render_json, render_text
from clarity.resolve import Resolved, config_line, profile_line, resolve

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


class CliError(Exception):
    """A user-facing error that maps to exit code 2."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clarity", description="Prose linter for AI-slop tics.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, helptext in (("check", "report findings"), ("score", "print the score only")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("path", nargs="?", help="file, or - for stdin")
        p.add_argument("--config", help="load only this file over the bundled pack")
        p.add_argument("--profile", help="profile name, or none")
        p.add_argument("--fail-under", type=float, default=80.0)
        p.add_argument("--min-confidence", choices=["exact", "inferred"], default="inferred")

        if name == "check":
            p.add_argument("--format", choices=["text", "json"], default="text")
            p.add_argument("--drift-baseline", help="add a drift section against this baseline")
            p.add_argument("--max-drift", type=float, help="exit 1 above this drift score")

    acc = sub.add_parser("accept", help="exempt a finding by id")
    acc.add_argument("finding_id")

    rules = sub.add_parser("rules", help="list active rules")
    rules.add_argument("--category", type=int)
    rules.add_argument("--config")
    rules.add_argument("--profile")

    cfg = sub.add_parser("config", help="print the resolved config with sources")
    cfg.add_argument("--config")
    cfg.add_argument("--profile")
    cfg.add_argument("--format", choices=["text", "json"], default="text")
    cfg.add_argument("--explain", metavar="RULE_ID")
    cfg.add_argument("--validate", action="store_true")

    sub.add_parser("init", help="create the user config directory with the default pack")

    t = sub.add_parser("test", help="run rule fixtures, corpus mode and snapshots")
    t.add_argument("target", nargs="?", help="a rule id or a fixture group")
    t.add_argument("--config")
    t.add_argument("--profile")
    t.add_argument("--changed", action="store_true", help="only rules changed vs git HEAD")
    t.add_argument("--corpus", help="false-positive rate against a corpus path")
    t.add_argument("--against", help="a second corpus; report the hit-rate ratio")
    t.add_argument("--corpus-ceiling", type=float, default=harness.CEILING)
    t.add_argument("--snapshots", action="store_true")
    t.add_argument("--fail-on-regression", action="store_true")

    ex = sub.add_parser("explain", help="why a rule did or did not match a text")
    ex.add_argument("rule_id")
    ex.add_argument("text", nargs="+", help="the text, or - for stdin")
    ex.add_argument("--config")
    ex.add_argument("--profile")

    sn = sub.add_parser("snapshot", help="record current findings as a baseline")
    sn.add_argument("path")
    sn.add_argument("--config")
    sn.add_argument("--profile")

    rep = sub.add_parser("repeats", help="list repeated phrases as candidate watchlist YAML")
    rep.add_argument("path", nargs="?", help="file, or - for stdin")
    rep.add_argument("--min-occurrences", type=int, default=3)
    rep.add_argument("--since", help="file of terms already listed; skip those")

    bl = sub.add_parser("baseline", help="build and inspect metric baselines")
    actions = bl.add_subparsers(dest="action", required=True)
    build = actions.add_parser("build", help="measure a corpus and store its baseline")
    build.add_argument("corpus")
    build.add_argument("--name", default="default")
    build.add_argument("--config")
    build.add_argument("--profile")
    actions.add_parser("list", help="list stored baselines")
    show = actions.add_parser("show", help="print a baseline")
    show.add_argument("name")

    dr = sub.add_parser("drift", help="how far a document sits from a baseline")
    dr.add_argument("path", nargs="?", help="file, or - for stdin")
    dr.add_argument("--baseline", default="default")
    dr.add_argument("--format", choices=["text", "json"], default="text")
    dr.add_argument("--config")
    dr.add_argument("--profile")

    tr = sub.add_parser("trend", help="a habit across a document's history or a folder of drafts")
    tr.add_argument("path")
    tr.add_argument("--metric")
    tr.add_argument("--rule")
    tr.add_argument("--config")
    tr.add_argument("--profile")

    sf = sub.add_parser("surface", help="everything a rule can address: fields, metrics, functions")
    for name in surface.SECTIONS:
        sf.add_argument(f"--{name}", action="store_true", help=f"only the {name} section")

    sf.add_argument("--format", choices=["markdown", "json"], default="markdown")
    sf.add_argument("--sync", metavar="FILE", help="rewrite the surface regions of a markdown file")
    sf.add_argument("--check", action="store_true", help="with --sync: exit 1 if the file is stale")
    sf.add_argument("--config")
    sf.add_argument("--profile")

    sub.add_parser("mcp", help="serve MCP over stdio")

    return parser


def _require_utf8(text: str) -> str:
    """Reject lone surrogates, which a C-locale Python uses for undecodable input bytes."""
    text.encode("utf-8")

    return text


def _read_source(path: str | None, stdin: TextIO) -> tuple[str, str]:
    """Return (text, source label). Stdin when path is - or absent and stdin is piped."""
    if path == "-" or (path is None and not stdin.isatty()):
        try:
            return _require_utf8(stdin.read()), SOURCE_STDIN
        except UnicodeDecodeError as exc:
            raise CliError(f"{SOURCE_STDIN} is not valid UTF-8 ({exc.reason})") from exc
        except UnicodeEncodeError as exc:
            raise CliError(f"{SOURCE_STDIN} is not valid UTF-8 ({exc.reason})") from exc

    if path is None:
        raise CliError("no path given and stdin is a terminal; pass a file or pipe text in")

    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), path
    except UnicodeDecodeError as exc:
        raise CliError(f"{path} is not valid UTF-8 ({exc.reason})") from exc
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror}") from exc


def _use_color(stream: TextIO) -> bool:
    return stream.isatty() and "NO_COLOR" not in os.environ


def _resolve(args: argparse.Namespace, path: str | None = None) -> Resolved:
    """Resolve config from the input file's directory, or the working directory for stdin."""
    start = Path(path).resolve().parent if path not in (None, "-") else Path.cwd()
    explicit = Path(args.config).resolve() if getattr(args, "config", None) else None

    return resolve(explicit, start, getattr(args, "profile", None))


def _analyze(args: argparse.Namespace, stdin: TextIO) -> tuple[dict[str, Any], str]:
    text, source = _read_source(args.path, stdin)
    resolved = _resolve(args, args.path)
    result = analyze(
        text,
        source=source,
        config=resolved.config,
        min_confidence=args.min_confidence,
        accepted=load_accepted(),
    )
    result["config_sources"] = resolved.files
    result["profile"] = (
        {"name": resolved.profile.name, "path": resolved.profile.path} if resolved.profile else None
    )
    result["config_line"] = config_line(resolved)
    result["profile_line"] = profile_line(resolved)

    if getattr(args, "max_drift", None) is not None and not args.drift_baseline:
        raise CliError("--max-drift needs --drift-baseline")

    if getattr(args, "drift_baseline", None):
        result["drift"] = baseline.drift(
            result["prose_metrics"]["metrics"], baseline.load(args.drift_baseline)
        )

    return result, source


def _exit_code(result: dict[str, Any], fail_under: float, max_drift: float | None = None) -> int:
    band = result["readability"]

    if result["score"] < fail_under:
        return EXIT_FAIL

    if max_drift is not None and result["drift"]["score"] > max_drift:
        return EXIT_FAIL

    if band["fail_outside_band"] and band["inside_band"] is False:
        return EXIT_FAIL

    return EXIT_OK


def _cmd_test(args: argparse.Namespace, stdout: TextIO) -> int:
    resolved = _resolve(args)
    failed = False

    if args.corpus:
        corpus = harness.scan_corpus(Path(args.corpus), resolved)
        text, flagged = harness.format_corpus(corpus, args.corpus_ceiling)
        stdout.write(text + "\n")
        failed = bool(flagged)

        if args.against:
            other = harness.scan_corpus(Path(args.against), resolved)
            stdout.write("\n" + harness.format_against(corpus, other) + "\n")
    elif args.snapshots:
        _, unexplained = harness.diff_snapshots(lambda p: _resolve(args, str(p)), stdout)
        failed = unexplained > 0
    else:
        only = harness.changed_rules(resolved) if args.changed else None
        index = fixtures_index(resolved)
        results = harness.run_fixtures(resolved.config, index, args.target, only)

        if args.target and not results:
            raise CliError(f"no fixtures for {args.target!r}")

        stdout.write(harness.format_results(results) + "\n")
        failed = any(not r.passed for r in results)

    return EXIT_FAIL if failed and (args.fail_on_regression or not args.corpus) else EXIT_OK


def fixtures_index(resolved: Resolved) -> dict[str, Any]:
    from clarity.fixtures import load_index

    return load_index(resolved.folders)


def _cmd_explain(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    from clarity.explain import explain

    resolved = _resolve(args)
    rule = next((r for r in resolved.config.rules if r.id == args.rule_id), None)

    if rule is None:
        raise CliError(f"unknown rule {args.rule_id!r}")

    text = stdin.read() if args.text == ["-"] else " ".join(args.text)
    stdout.write(explain(rule, text, resolved) + "\n")

    return EXIT_OK


def _cmd_config(args: argparse.Namespace, stdout: TextIO) -> int:
    resolved = _resolve(args)

    if args.validate:
        stdout.write(config_cmds.validate(resolved) + "\n")
    elif args.explain:
        stdout.write(config_cmds.explain_rule(resolved, args.explain) + "\n")
    else:
        stdout.write(config_cmds.render(resolved, args.format) + "\n")

    return EXIT_OK


def _cmd_baseline(args: argparse.Namespace, stdout: TextIO) -> int:
    if args.action == "build":
        made = baseline.build(Path(args.corpus), args.name, _resolve(args).config)
        stdout.write(f"{made['name']}: {made['documents']} documents · {made['words']:,} words · "
                     f"{len(made['metrics'])} metrics\nwritten to {made['path']}\n")  # fmt: skip
    elif args.action == "list":
        stdout.write("".join(f"{n}\n" for n in baseline.names()))
    else:
        stdout.write(baseline.format_show(baseline.load(args.name)) + "\n")

    return EXIT_OK


def _cmd_drift(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    text, source = _read_source(args.path, stdin)
    result = analyze(text, source=source, config=_resolve(args, args.path).config)
    found = baseline.drift(result["prose_metrics"]["metrics"], baseline.load(args.baseline))

    if args.format == "json":
        stdout.write(json.dumps(found, indent=2) + "\n")
    else:
        stdout.write(baseline.format_drift(found) + "\n")

    return EXIT_OK


def _cmd_trend(args: argparse.Namespace, stdout: TextIO) -> int:
    resolved = _resolve(args, args.path)
    rows = baseline.history(Path(args.path), resolved.config)
    rule = next((r for r in resolved.config.rules if r.id == args.rule), None)

    if args.rule and rule is None:
        raise CliError(f"unknown rule {args.rule!r}")

    allowance = rule.max_per_1k if rule and rule.count_scope == "document" else None
    stdout.write(baseline.format_trend(rows, args.rule, args.metric, allowance) + "\n")

    return EXIT_OK


def _cmd_surface(args: argparse.Namespace, stdout: TextIO) -> int:
    data = surface.build(_resolve(args).config)

    if args.sync:
        stale = surface.sync(Path(args.sync), data, write=not args.check)
        stdout.write(("stale: " + ", ".join(stale) if stale else "up to date") + "\n")

        return EXIT_FAIL if stale and args.check else EXIT_OK

    chosen = tuple(n for n in surface.SECTIONS if getattr(args, n))

    if args.format == "json":
        shown = {n: data[n] for n in chosen or surface.SECTIONS}
        stdout.write(json.dumps(shown, indent=2) + "\n")
    else:
        stdout.write(surface.markdown(data, chosen or surface.SECTIONS) + "\n")

    return EXIT_OK


def _cmd_rules(args: argparse.Namespace, stdout: TextIO) -> int:
    config = _resolve(args).config

    if args.category is not None and args.category not in config.categories:
        raise CliError(f"unknown category {args.category}")

    for row in describe_rules(config, args.category):
        if row["count_scope"] == "document":
            allowance = f"max_per_1k={row['max_per_1k']:g}"
        else:
            allowance = f"max_per_scope={row['max_per_scope']} per {row['count_scope']}"

        where = "" if row["position"] == "anywhere" else f"  [{row['position']}]"
        stdout.write(
            f"{row['category_number']:>2} {row['category']:<22} {row['id']:<30} "
            f"{row['severity']:<8} {row['confidence']:<9} {allowance}{where}\n"
        )

    return EXIT_OK


def _cmd_repeats(args: argparse.Namespace, stdin: TextIO, stdout: TextIO) -> int:
    from clarity.nlp import get_nlp
    from clarity.repeats import repeated_ngrams

    text, _ = _read_source(args.path, stdin)
    known = ""

    if args.since:
        try:
            known = Path(args.since).read_text(encoding="utf-8").lower()
        except OSError as exc:
            raise CliError(f"cannot read {args.since}: {exc.strerror}") from exc

    found = repeated_ngrams(get_nlp()(text), min_occurrences=args.min_occurrences)
    fresh = [r for r in found if r.phrase not in known]

    if not fresh:
        stdout.write("# no repeated phrases found\n")

        return EXIT_OK

    stdout.write("# Paste into clarity.yml to list a repeated phrase.\nwatchlist:\n")

    for rep in fresh:
        entry = f'{{term: "{rep.phrase}", max_per_1k: 0, match: phrase}}'
        stdout.write(f"  - {entry}  # {len(rep.spans)} times\n")

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

        if args.command == "surface":
            return _cmd_surface(args, stdout)

        if args.command == "baseline":
            return _cmd_baseline(args, stdout)

        if args.command == "drift":
            return _cmd_drift(args, stdin, stdout)

        if args.command == "trend":
            return _cmd_trend(args, stdout)

        if args.command == "init":
            return config_cmds.init(stdout)

        if args.command == "config":
            return _cmd_config(args, stdout)

        if args.command == "test":
            return _cmd_test(args, stdout)

        if args.command == "explain":
            return _cmd_explain(args, stdin, stdout)

        if args.command == "snapshot":
            harness.take_snapshot(Path(args.path), _resolve(args, args.path), stdout)

            return EXIT_OK

        if args.command == "repeats":
            return _cmd_repeats(args, stdin, stdout)

        result, source = _analyze(args, stdin)
    except (CliError, ConfigError, ModelError, InputError, baseline.BaselineError) as exc:
        stderr.write(f"clarity: {exc}\n")

        return EXIT_ERROR

    if args.command == "score":
        stdout.write(f"{result['score']:g}\n")
    elif args.format == "json":
        stdout.write(render_json(result, source) + "\n")
    else:
        stdout.write(render_text(result, source, _use_color(stdout), args.fail_under) + "\n")

    return _exit_code(result, args.fail_under, getattr(args, "max_drift", None))


if __name__ == "__main__":
    sys.exit(main())
