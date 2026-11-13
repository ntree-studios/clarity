"""clarity surface: what a rule can address, and the docs that are rendered from it."""

import json
import re
import shutil
from dataclasses import fields
from pathlib import Path

import pytest
from test_cli import run
from test_mcp import start

from clarity import surface
from clarity.config import BACKEND_FIELDS, BACKEND_REQUIRES, Rule, load_config
from clarity.metrics import load_registry

README = Path(__file__).resolve().parent.parent / "README.md"


def data():
    return surface.build(load_config(None))


def test_the_readme_surface_regions_are_present_and_current():
    text = README.read_text(encoding="utf-8")

    assert {n for n in surface.SECTIONS if f"<!-- surface:{n} -->" in text} >= {
        "fields", "enums", "conditions", "metrics", "functions", "categories", "mcp",
    }  # fmt: skip
    assert surface.sync(README, data(), write=False) == [], (
        "a README surface region is stale: run clarity surface --sync README.md"
    )


def test_every_rule_field_is_documented_and_every_backend_field_exists():
    names = {f.name for f in fields(Rule)}

    assert names <= set(surface.FIELD_DOCS)
    assert {n for group in BACKEND_FIELDS.values() for n in group} <= names
    assert {n for opts in BACKEND_REQUIRES.values() for o in opts for n in o} <= names
    assert all(row["description"] for row in surface.rule_fields())


def test_the_surface_lists_every_registered_metric_and_structural_function():
    from clarity.matchers.structural import REGISTRY

    found = data()

    assert {m["name"] for m in found["metrics"]} == set(load_registry())
    assert {f["name"] for f in found["functions"]} == set(REGISTRY)
    assert found["sets"]["names"] == []


def test_the_cli_prints_sections_and_json():
    code, out, _ = run(["surface", "--metrics"])

    assert code == 0 and "subordination_index" in out and "## fields" not in out

    code, out, _ = run(["surface", "--fields", "--enums", "--format", "json"])

    assert set(json.loads(out)) == {"fields", "enums"}
    assert "phrases" in {f["name"] for f in json.loads(out)["fields"]}


def test_sync_reports_stale_regions_and_rewrites_them(tmp_path):
    copy = tmp_path / "doc.md"
    shutil.copy(README, copy)
    copy.write_text(re.sub(r"(<!-- surface:enums -->\n).*?(\n<!-- /surface:enums -->)",
                           r"\1- stale\2", copy.read_text(), flags=re.DOTALL))  # fmt: skip

    assert run(["surface", "--sync", str(copy), "--check"])[0] == 1
    assert "stale: enums" in run(["surface", "--sync", str(copy)])[1]
    assert run(["surface", "--sync", str(copy), "--check"])[0] == 0


def test_the_mcp_server_serves_the_surface_and_lists_what_the_readme_lists():
    session = start()

    try:
        text = session.call("resources/read", {"uri": "clarity://surface"})["result"]["contents"][
            0
        ]["text"]
        tools = {t["name"] for t in session.call("tools/list")["result"]["tools"]}
        prompts = {p["name"] for p in session.call("prompts/list")["result"]["prompts"]}
        got = session.call("prompts/get", {"name": "bootstrap_rules",
                                           "arguments": {"good_corpus_path": "/g",
                                                         "bad_corpus_path": "/b"}})  # fmt: skip
    finally:
        session.close()

    served = json.loads(text)

    assert set(served["mcp"]["tools"]) == tools and set(served["mcp"]["prompts"]) == prompts
    assert "clarity://surface" in got["result"]["messages"][0]["content"]["text"]


def test_the_readme_uses_one_spelling_for_turning_a_rule_off():
    blocks = re.findall(r"```yaml\n(.*?)```", README.read_text(encoding="utf-8"), re.DOTALL)

    assert not [b for b in blocks if "disabled:" in b]


@pytest.mark.parametrize("section", surface.SECTIONS)
def test_every_section_renders(section):
    assert surface.render(section, data()).strip()
