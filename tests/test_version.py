"""Guard D-83: the package version and the project version change together."""

import tomllib
from pathlib import Path

import pycon_us

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_matches_pyproject() -> None:
    """``pycon_us.__version__`` equals ``pyproject.toml``'s ``[project] version``."""
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert pycon_us.__version__ == project["version"]
