"""Every YAML block in the docs must load. Docs that drift from the schema fail the build."""

import re
from importlib import resources
from pathlib import Path

import pytest
import yaml

from clarity.config import ConfigError, load_config
from clarity.fixtures import load_file

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", *sorted((ROOT / "src" / "clarity" / "guides").glob("*.md"))]
FENCE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)


def blocks():
    for doc in DOCS:
        for n, match in enumerate(FENCE.finditer(doc.read_text(encoding="utf-8")), start=1):
            yield pytest.param(match.group(1), id=f"{doc.name}#{n}")


@pytest.mark.parametrize("block", list(blocks()))
def test_yaml_block_validates(block, tmp_path):
    data = yaml.safe_load(block)

    if isinstance(data, dict) and "rule" in data:
        path = tmp_path / "doc.test.yml"
        path.write_text(block, encoding="utf-8")
        found = load_file(path)

        assert found and found[0].fire and found[0].no_fire

        return

    if isinstance(data, list):
        data = {"rules": data}

    try:
        load_config(text=yaml.safe_dump(data))
    except ConfigError as exc:
        pytest.fail(f"does not load: {exc}")


def test_the_readme_category_list_matches_the_shipped_pack():
    lines = (ROOT / "README.md").read_text().splitlines()
    line = next(ln for ln in lines if ln.startswith("Categories:"))
    shown = re.findall(r"(\d+) ([a-z]+)", line)
    pack = yaml.safe_load(resources.files("clarity").joinpath("default.yml").read_text())

    assert [(int(n), name) for n, name in shown] == [
        (c["n"], c["id"].split("-")[0]) for c in pack["categories"]
    ]
