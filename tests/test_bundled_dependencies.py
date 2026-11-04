"""What reaches phones is declared and pinned in `pyproject.toml` (D-75, D-470).

`flet build` never reads `uv.lock`: pip resolves `[project].dependencies` when the build
runs. So a package the app imports but gets through another package's range ships in whatever
version pip finds that day, unlike the one the tests ran.
"""

import ast
import sys
import tomllib
from collections.abc import Container
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
# The app itself, and the type checker's stubs, imported only under TYPE_CHECKING.
NOTHING_TO_BUNDLE = {"pycon_us", "_typeshed"}


def read_pyproject() -> dict:
    """The repository's `pyproject.toml`, parsed."""
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def bundled_requirements() -> list[Requirement]:
    """The requirements `flet build` hands pip."""
    return [Requirement(line) for line in read_pyproject()["project"]["dependencies"]]


def imported_top_level(source: str) -> set[str]:
    """Return the top-level names that `source`'s absolute imports name."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {alias.name.partition(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.partition(".")[0])
    return names


def undeclared_imports(sources: list[str], declared: Container[str]) -> set[str]:
    """Return what `sources` import that is not the standard library's, ours or declared."""
    imported = set().union(*map(imported_top_level, sources))
    third_party = imported - set(sys.stdlib_module_names) - NOTHING_TO_BUNDLE
    return {name for name in third_party if canonicalize_name(name) not in declared}


def test_every_package_the_app_imports_is_declared() -> None:
    """Each third-party package imported under `src/` is in `[project].dependencies`."""
    sources = [
        path.read_text(encoding="utf-8") for path in (ROOT / "src").rglob("*.py")
    ]
    declared = {canonicalize_name(req.name) for req in bundled_requirements()}
    assert "httpx" in declared
    assert undeclared_imports(sources, declared) == set()


def test_an_undeclared_import_is_reported_by_name() -> None:
    """A package imported but not declared fails the check; a submodule counts as its package."""
    sources = ["import json\nimport pycon_us.config\nfrom leftpad.core import pad\n"]
    assert undeclared_imports(sources, declared=set()) == {"leftpad"}


def test_every_bundled_package_is_pinned_exactly() -> None:
    """A requirement says `==`, unless `.flet-ref` pins it through `dev_packages` (D-81)."""
    from_flet_ref = set(read_pyproject()["tool"]["flet"]["dev_packages"])
    for requirement in bundled_requirements():
        if requirement.name in from_flet_ref:
            continue
        operators = [spec.operator for spec in requirement.specifier]
        assert operators == ["=="], requirement
