"""STDIO MCP server. Stdout carries protocol frames only; all logging goes to stderr."""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from clarity import bootstrap, prompts, surface, topics
from clarity.config import Config, _parse
from clarity.config import describe_rules as describe
from clarity.engine import analyze, contract
from clarity.nlp import ModelError
from clarity.resolve import ENV_CONFIG, ENV_PROFILE, resolve, switches

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


FOCUS_DOC = """focus is optional: {keywords: [str], description: str, named: {name: {keywords:
    [str], description: str}}}. It says what the text is supposed to be about. Keywords join the
    topic vocabulary even when rare, add to the anchor, and are counted per chunk and section."""

SWITCH_DOC = """disable and enable are optional lists of rule ids or category ids (clarity://rules
    lists both). A category id stands for every rule in it. They apply after the config and the
    profile, disables first, so enable can turn one rule back on inside a disabled category or
    turn on a rule that is off by default. An unknown id is an error."""


def _focus_doc[**Q, T](fn: Callable[Q, T]) -> Callable[Q, T]:
    """Put the focus and disable/enable argument schemas in the tool description clients see."""
    fn.__doc__ = (fn.__doc__ or "").replace("{focus}", FOCUS_DOC).replace("{switch}", SWITCH_DOC)

    return fn


def _config(
    profile: str | None = None,
    text: str | None = None,
    focus: dict[str, Any] | None = None,
    disable: list[str] | None = None,
    enable: list[str] | None = None,
) -> Config:
    """The config the CLI would use in the working directory (shipped pack and profiles, user and
    project .clarity/, or the server's --config), with profile, clarity.yml text, disable and
    enable, and focus applied on top."""
    extra = _parse(text) if text else None
    config = resolve(None, Path.cwd(), profile, extra, switches(disable, enable)).config

    if focus:
        config.topics = topics.effective(config.topics, {"focus": focus})

    return config


@server.tool()
@_reports(ToolError)
@_focus_doc
def check_text(
    text: str | None = None,
    document: dict[str, Any] | None = None,
    config: str | None = None,
    focus: dict[str, Any] | None = None,
    profile: str | None = None,
    disable: list[str] | None = None,
    enable: list[str] | None = None,
) -> dict[str, Any]:
    """Lint prose. Send text (a plain string, one section) or document (a section tree; read
    clarity://guide/document for how to break content into sections). Returns the document score
    and the section tree: each section's own findings, categories, score, and a rollup score
    over it and its child sections. Findings give the field (title, subtitle, text, items[i])
    and offsets, line and column inside that field. clarity://guide/usage covers choosing a
    profile, which rules to switch off and how to read the findings.

    Uses the same config as the CLI in the working directory: the shipped rules and profiles,
    then ~/.clarity and the project .clarity/ (or the server's --config). profile is a profile name
    (technical, business, essay, or one of your own; "none" for no profile). config is optional
    clarity.yml text applied on top. {switch} {focus}
    """
    config_ = _config(profile, config, focus, disable, enable)

    return contract(analyze(_input(text, document), source=SOURCE, config=config_))


@server.tool()
@_reports(ToolError)
@_focus_doc
def score_text(
    text: str | None = None,
    document: dict[str, Any] | None = None,
    focus: dict[str, Any] | None = None,
    profile: str | None = None,
    disable: list[str] | None = None,
    enable: list[str] | None = None,
) -> dict[str, Any]:
    """Style score (0-100) and readability, with the same input and config as check_text.
    profile is a profile name, or "none". {switch} {focus}"""
    config = _config(profile, None, focus, disable, enable)
    result = analyze(_input(text, document), source=SOURCE, config=config)

    return {"score": result["score"], "readability": result["readability"]}


def _input(text: str | None, document: dict[str, Any] | None) -> str | dict[str, Any]:
    """Exactly one of text and document."""
    if (text is None) == (document is None):
        raise ValueError("send either text (a plain string) or document (a section tree)")

    return document if document is not None else str(text)


@server.tool()
@_reports(ToolError)
@_focus_doc
def analyze_topics(
    text: str | None = None,
    document: dict[str, Any] | None = None,
    anchor: str | None = None,
    named: dict[str, str] | None = None,
    graph: bool = False,
    settings: dict[str, Any] | None = None,
    focus: dict[str, Any] | None = None,
    disable: list[str] | None = None,
    enable: list[str] | None = None,
) -> dict[str, Any]:
    """Topics, word shares, topic shifts and main/digression/drift runs from a chunk graph.
    Send text (a plain string) or document (a section tree, see clarity://guide/document).

    anchor is text the main topic should be closest to; by default the title. named maps a topic
    name to description words and adds alignment shares. settings overrides the topics: config
    block. With graph true, the result also carries the graph as node-link JSON. {switch}
    {focus}
    """
    from clarity.engine import parse

    overrides: dict[str, Any] = dict(settings or {})
    overrides.update({k: v for k, v in (("anchor", anchor), ("named", named), ("focus", focus))
                      if v})  # fmt: skip
    config = _config(disable=disable, enable=enable)
    settings_ = topics.effective(config.topics, overrides)
    result = topics.for_analysis(parse(_input(text, document), config), settings_)
    out = dict(result.report)

    if graph:
        out["graph"] = topics.graph_json(result)

    return out


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

    The score measures only the distance from the baseline.
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


@server.resource("clarity://surface", mime_type="application/json")
@_reports(ResourceError)
def resource_surface() -> str:
    """Every rule field, enum, condition, metric, structural function and category in use."""
    return _dump(surface.build(resolve(None, Path.cwd(), None).config))


@server.resource("clarity://guide/document", mime_type="text/markdown")
@_reports(ResourceError)
def resource_guide_document() -> str:
    """How to break content into sections for check_text, score_text and analyze_topics."""
    return _guide("document.md")


@server.resource("clarity://guide/usage", mime_type="text/markdown")
@_reports(ResourceError)
def resource_guide_usage() -> str:
    """How to use check_text on someone's writing: input shape, profile, rules to switch off,
    reading the findings."""
    return _guide("usage.md")


@server.resource("clarity://schema/document", mime_type="application/json")
@_reports(ResourceError)
def resource_schema_document() -> str:
    """JSON Schema of the document argument (input) and of the check_text response."""
    from clarity.structure import SCHEMA

    return _dump(SCHEMA)


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


def serve(config: list[str] | None = None, profile: str | None = None) -> None:
    """--config and --profile reach every tool and resource through the environment resolve()
    reads, so a client can also set CLARITY_CONFIG and CLARITY_PROFILE itself."""
    if config:
        os.environ[ENV_CONFIG] = os.pathsep.join(str(Path(c).resolve()) for c in config)

    if profile:
        os.environ[ENV_PROFILE] = profile

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    log.info("clarity mcp server starting on stdio")
    server.run("stdio")
