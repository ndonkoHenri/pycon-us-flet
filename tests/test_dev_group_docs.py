"""The docs that quote `pyproject.toml`'s `dev` group list the packages it lists."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _dev_group(path: str) -> list[str]:
    """Return the `dev` list of the `[dependency-groups]` table quoted in `path`."""
    text = (ROOT / path).read_text(encoding="utf-8")
    table = re.search(
        r"^\[dependency-groups\]\ndev = \[.*?^\]$", text, re.MULTILINE | re.DOTALL
    )
    assert table, f"no [dependency-groups] table with a dev list in {path}"
    return tomllib.loads(table.group())["dependency-groups"]["dev"]


@pytest.mark.parametrize("doc", ["docs/development.md", "docs/testing-and-quality.md"])
def test_quoted_dev_group_matches_the_project_file(doc: str) -> None:
    """A quoted `dev` list names the same packages as `pyproject.toml`, in the same order."""
    assert _dev_group(doc) == _dev_group("pyproject.toml")
