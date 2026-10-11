import tomllib
from pathlib import Path

import pycon_us

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_matches_pyproject():
    """``pycon_us.__version__`` and ``[project].version`` change together (D-83)."""
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert pycon_us.__version__ == project["version"]
