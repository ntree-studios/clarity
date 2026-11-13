"""The installed wheel must ship every bundled resource the code reads at runtime."""

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "clarity"


def declared_patterns() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    return data["tool"]["setuptools"]["package-data"]["clarity"]


def test_package_data_covers_the_default_rule_pack():
    assert any(fnmatch.fnmatch("default.yml", p) for p in declared_patterns())


def test_package_data_covers_the_concreteness_table():
    assert any(fnmatch.fnmatch("data/concreteness.tsv", p) for p in declared_patterns())


def test_root_clarity_yml_is_the_bundled_default():
    assert (ROOT / "clarity.yml").read_text() == (PACKAGE / "default.yml").read_text()


def test_license_is_mit_for_n_tree_studios():
    text = (ROOT / "LICENSE").read_text()
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert text.startswith("MIT License")
    assert "N-Tree Studios" in text
    assert data["project"]["license"] == "MIT"
