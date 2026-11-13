"""STDIO MCP server. Stdout carries protocol frames only; all logging goes to stderr."""

from __future__ import annotations

import functools
import json
import logging
import sys
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from clarity import bootstrap, prompts
from clarity.config import describe_rules as describe
from clarity.config import load_config
from clarity.engine import analyze
from clarity.nlp import ModelError
from clarity.resolve import resolve

SOURCE = "<text>"
log = logging.getLogger("clarity.mcp")
server = MCPServer("clarity")


P = ParamSpec("P")
R = TypeVar("R")
ANTICIPATED = (ValueError, OSError, ModelError)


def _reports(error: type[Exception]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Turn a failure the caller can act on into an error whose message the client sees."""

    def wrap(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def run(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return fn(*args, **kwargs)
            except ANTICIPATED as exc:
                raise error(str(exc)) from exc

        return run

    return wrap


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _guide(name: str) -> str:
    return resources.files("clarity").joinpath("guides", name).read_text(encoding="utf-8")


# ---- checking -----------------------------------------------------------------------------


@server.tool()
@_reports(ToolError)
def check_text(text: str, config: str | None = None) -> dict[str, Any]:
    """Lint prose. Returns findings, per-category breakdown, style score and readability.

    config is optional clarity.yml text merged over the default pack.
    """
    return analyze(text, source=SOURCE, config=load_config(text=config))


@server.tool()
@_reports(ToolError)
def score_text(text: str) -> dict[str, Any]:
    """Style score (0-100) and readability for the text."""
    result = analyze(text, source=SOURCE)

    return {"score": result["score"], "readability": result["readability"]}


@server.tool()
@_reports(ToolError)
def list_rules() -> list[dict[str, Any]]:
    """List the active rules, including those in the working directory's .clarity folder."""
    return describe(resolve(None, Path.cwd(), None).config)


@server.tool()
@_reports(ToolError)
def accept_finding(finding_id: str) -> dict[str, Any]:
    """Exempt a finding by the six-character id shown in a report."""
    return bootstrap.accept_finding(finding_id)


# ---- bootstrap: measurement ---------------------------------------------------------------


@server.tool()
@_reports(ToolError)
def corpus_stats(path: str) -> dict[str, Any]:
    """Document count, word count, average prose metrics and rule hit rates for a folder.

    reliability is insufficient (under 10 documents or 5,000 words), provisional (under 25
    documents or 20,000 words) or reliable.
    """
    return bootstrap.corpus_stats(path)


@server.tool()
@_reports(ToolError)
def suggest_rules(
    good_path: str,
    bad_path: str,
    n_range: list[int] | None = None,
    min_occurrences: int = 5,
) -> dict[str, Any]:
    """N-grams ranked by log-odds of appearing in the bad corpus over the good one.

    Refuses a corpus under 10 documents or 5,000 words. n_range is [min, max] words, default
    [1, 3]. Candidates are hypotheses: measure each with test_rule.
    """
    low, high = (n_range or [1, 3])[:2] if n_range and len(n_range) >= 2 else (1, 3)

    return bootstrap.suggest_rules(good_path, bad_path, (low, high), min_occurrences)


@server.tool()
@_reports(ToolError)
def test_rule(rule_definition: dict[str, Any], good_path: str, bad_path: str) -> dict[str, Any]:
    """Measure an unsaved rule against both corpora: rates per 1,000 words, ratio, verdict.

    This is the gate every proposal passes through. A ratio under 3.0 gets verdict discard, and
    write_rules will refuse the rule. Refuses a corpus under 10 documents or 5,000 words.
    """
    return bootstrap.measure_rule(rule_definition, good_path, bad_path)


@server.tool()
@_reports(ToolError)
def find_matches(
    path: str,
    rule_id: str | None = None,
    rule_definition: dict[str, Any] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Real sentences a rule matches in a folder, with file and line. Give rule_id or a
    definition."""
    return bootstrap.find_matches(rule_id, rule_definition, path, limit)


@server.tool()
@_reports(ToolError)
def get_rule(rule_id: str) -> dict[str, Any]:
    """The resolved definition of a rule with the file that set each field."""
    return bootstrap.get_rule(rule_id)


@server.tool()
@_reports(ToolError)
def get_metrics(text: str) -> dict[str, Any]:
    """The full prose metrics block: structure, variety, register and document metrics."""
    return bootstrap.get_metrics(text)


@server.tool()
@_reports(ToolError)
def build_baseline(corpus_path: str, name: str = "default") -> dict[str, Any]:
    """Store the mean and spread of every metric across a corpus as .clarity/baselines/NAME.json.

    Refuses under 25 documents or 20,000 words.
    """
    return bootstrap.build_baseline(corpus_path, name)


@server.tool()
@_reports(ToolError)
def measure_drift(text: str, baseline: str = "default") -> dict[str, Any]:
    """z-score of each metric for a text against a stored baseline.

    The score is a distance from the baseline, not a verdict on the writing.
    """
    return bootstrap.measure_drift(text, baseline)


@server.tool()
@_reports(ToolError)
def test_composite(
    rule_definition: dict[str, Any], good_path: str, bad_path: str
) -> dict[str, Any]:
    """Measure a composite rule and each member rule against both corpora.

    Returns the composite's ratio, each member's ratio and beats_members. A composite that does
    not beat every member gets verdict discard, and write_rules refuses it.
    """
    return bootstrap.measure_composite(rule_definition, good_path, bad_path)


# ---- bootstrap: fixtures and writes -------------------------------------------------------


@server.tool()
@_reports(ToolError)
def validate_fixtures(rule_id: str, fixtures: dict[str, Any]) -> dict[str, Any]:
    """Pass or fail for each proposed fixture case against the rule's current definition.

    fixtures is {should_fire: [...], should_not_fire: [...]}. A case is a string or
    {text, expect: {count, span}}. The minimum is 1 should_fire and 2 should_not_fire.
    """
    return bootstrap.validate_fixtures(rule_id, fixtures)


@server.tool()
@_reports(ToolError)
def write_rules(
    rules: list[dict[str, Any]], user_approved: bool, target: str = "workdir"
) -> dict[str, Any]:
    """Write rules the user accepted to bootstrap.yml. Returns the path and any rejections.

    Show the user the exact YAML first and pass user_approved true only after they accept it.
    Only rules measured by test_rule with a ratio of 3.0 or more are written; others come back
    in rejected with the reason. target is workdir (default, the project .clarity folder) or user.
    """
    return bootstrap.write_rules(rules, user_approved, target)


@server.tool()
@_reports(ToolError)
def write_fixtures(
    rule_id: str, fixtures: dict[str, Any], user_approved: bool, target: str = "workdir"
) -> dict[str, Any]:
    """Write fixtures the user accepted to bootstrap.test.yml and take the rule out of
    experimental.

    Show the user the exact cases first and pass user_approved true only after they accept them.
    The set must meet the minimum and pass against the current rule.
    """
    return bootstrap.write_fixtures(rule_id, fixtures, user_approved, target)


# ---- resources ----------------------------------------------------------------------------


@server.resource("clarity://config/resolved", mime_type="application/json")
@_reports(ResourceError)
def resource_config() -> str:
    from clarity import config_cmds

    return config_cmds.render(resolve(None, Path.cwd(), None), "json")


@server.resource("clarity://rules", mime_type="application/json")
@_reports(ResourceError)
def resource_rules() -> str:
    return _dump(describe(resolve(None, Path.cwd(), None).config))


@server.resource("clarity://rules/{rule_id}", mime_type="application/json")
@_reports(ResourceError)
def resource_rule(rule_id: str) -> str:
    return _dump(bootstrap.get_rule(rule_id))


@server.resource("clarity://categories", mime_type="application/json")
@_reports(ResourceError)
def resource_categories() -> str:
    return _dump(bootstrap.categories())


@server.resource("clarity://profiles", mime_type="application/json")
@_reports(ResourceError)
def resource_profiles() -> str:
    return _dump(bootstrap.profiles())


@server.resource("clarity://schema/rule", mime_type="text/markdown")
@_reports(ResourceError)
def resource_schema_rule() -> str:
    return _guide("schema-rule.md")


@server.resource("clarity://schema/fixture", mime_type="text/markdown")
@_reports(ResourceError)
def resource_schema_fixture() -> str:
    return _guide("schema-fixture.md")


@server.resource("clarity://schema/composite", mime_type="text/markdown")
@_reports(ResourceError)
def resource_schema_composite() -> str:
    return _guide("schema-composite.md")


@server.resource("clarity://baselines", mime_type="application/json")
@_reports(ResourceError)
def resource_baselines() -> str:
    return _dump(bootstrap.baselines_list())


@server.resource("clarity://baselines/{name}", mime_type="application/json")
@_reports(ResourceError)
def resource_baseline(name: str) -> str:
    return _dump(bootstrap.baseline_show(name))


@server.resource("clarity://metrics/schema", mime_type="application/json")
@_reports(ResourceError)
def resource_metrics_schema() -> str:
    return _dump(bootstrap.metrics_schema())


@server.resource("clarity://guide/authoring", mime_type="text/markdown")
@_reports(ResourceError)
def resource_guide_authoring() -> str:
    return _guide("guide-authoring.md")


@server.resource("clarity://guide/calibration", mime_type="text/markdown")
@_reports(ResourceError)
def resource_guide_calibration() -> str:
    return _guide("guide-calibration.md")


# ---- prompts ------------------------------------------------------------------------------


@server.prompt()
def bootstrap_rules(good_corpus_path: str, bad_corpus_path: str, focus: str = "") -> str:
    """Build a measured rule pack from a folder of good writing and a folder of bad writing."""
    return prompts.bootstrap_rules(good_corpus_path, bad_corpus_path, focus)


@server.prompt()
def bootstrap_composites(good_corpus_path: str, bad_corpus_path: str) -> str:
    """Find rule co-occurrences that separate the corpora better than either rule alone."""
    return prompts.bootstrap_composites(good_corpus_path, bad_corpus_path)


@server.prompt()
def bootstrap_fixtures(rule_id: str) -> str:
    """Write fixtures for a rule from real hits in the user's corpora."""
    return prompts.bootstrap_fixtures(rule_id)


@server.prompt()
def tune_rule(rule_id: str) -> str:
    """Sweep a rule's threshold and recommend a value with the tradeoff stated."""
    return prompts.tune_rule(rule_id)


def serve() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    log.info("clarity mcp server starting on stdio")
    server.run("stdio")
