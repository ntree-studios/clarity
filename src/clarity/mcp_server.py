"""STDIO MCP server. Stdout carries protocol frames only; all logging goes to stderr."""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from clarity.config import describe_rules as describe
from clarity.config import load_config
from clarity.engine import analyze

SOURCE = "<text>"
log = logging.getLogger("clarity.mcp")
server = MCPServer("clarity")


@server.tool()
def check_text(text: str, config: str | None = None) -> dict[str, Any]:
    """Lint prose. Returns findings, per-category breakdown, style score and readability.

    config is optional clarity.yml text merged over the default pack.
    """
    return analyze(text, source=SOURCE, config=load_config(text=config))


@server.tool()
def score_text(text: str) -> dict[str, Any]:
    """Style score (0-100) and readability for the text."""
    result = analyze(text, source=SOURCE)

    return {"score": result["score"], "readability": result["readability"]}


@server.tool()
def list_rules() -> list[dict[str, Any]]:
    """List the active rules."""
    return describe(load_config(None))


def serve() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    log.info("clarity mcp server starting on stdio")
    server.run("stdio")
