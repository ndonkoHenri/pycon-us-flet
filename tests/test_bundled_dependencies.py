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


def is_flet(name: str) -> bool:
    """Say whether `name` is a package of the Flet family."""
    return name == "flet" or name.startswith("flet-")


def checkout_names(tool: dict, bundled: set[str]) -> set[str]:
    """Return the Flet packages a temporary source build truly takes from a checkout.

    uv's table serves the host. A package that reaches phones needs `flet build`'s table too,
    or pip would resolve it from PyPI (`docs/development.md` §2.2).

    Args:
        tool: The `[tool]` table of `pyproject.toml`.
        bundled: The names in `[project].dependencies`.

    Returns:
        The names the pin tests allow to go unpinned.
    """
    sources = set(tool.get("uv", {}).get("sources", {}))
    for_phones = set(tool.get("flet", {}).get("dev_packages", {}))
    return {
        name
        for name in sources
        if is_flet(name) and (name not in bundled or name in for_phones)
    }


def from_a_flet_checkout() -> set[str]:
    """What a temporary source build of Flet takes from a checkout, by `pyproject.toml`."""
    bundled = {requirement.name for requirement in bundled_requirements()}
    return checkout_names(read_pyproject()["tool"], bundled)


def test_a_bundled_package_needs_both_tables_to_go_unpinned() -> None:
    """A uv source alone doesn't excuse a package that reaches phones; a host tool needs only it."""
    tool: dict = {
        "uv": {"sources": {"flet-notifications": {}, "flet-cli": {}, "httpx": {}}}
    }
    assert checkout_names(tool, {"flet-notifications", "httpx"}) == {"flet-cli"}
    tool["flet"] = {"dev_packages": {"flet-notifications": "path"}}
    assert checkout_names(tool, {"flet-notifications", "httpx"}) == {
        "flet-cli",
        "flet-notifications",
    }


def test_every_bundled_package_is_pinned_exactly() -> None:
    """A requirement says `==`, unless a temporary source build of Flet supplies it."""
    for requirement in bundled_requirements():
        if requirement.name in from_a_flet_checkout():
            continue
        operators = [spec.operator for spec in requirement.specifier]
        assert operators == ["=="], requirement


def family_versions(requirements: list[Requirement]) -> dict[str, set[str]]:
    """Return each Flet package's pinned versions; a requirement with no `==` gives `""`."""
    versions: dict[str, set[str]] = {}
    for requirement in requirements:
        if is_flet(requirement.name):
            pins = [s.version for s in requirement.specifier if s.operator == "=="]
            versions.setdefault(requirement.name, set()).update(pins or [""])
    return versions


def test_family_versions_tell_a_disagreement_from_agreement() -> None:
    """Two versions, and a package with no exact pin, both show in what the check reads."""
    requirements = [
        Requirement(line) for line in ("flet==1", "flet-cli==2", "flet-web", "httpx==3")
    ]
    assert family_versions(requirements) == {
        "flet": {"1"},
        "flet-cli": {"2"},
        "flet-web": {""},
    }


def test_the_flet_family_shares_one_version() -> None:
    """Every Flet package in `pyproject.toml`, the dev tools included, pins the same version.

    The wheels pin each other, but pip and uv would then just fail to resolve; and the Dart side
    comes from the release of `flet-cli`'s version, so a mix builds another Flet than it runs.
    """
    pyproject = read_pyproject()
    lines = [
        *pyproject["project"]["dependencies"],
        *pyproject["dependency-groups"]["dev"],
    ]
    versions = family_versions([Requirement(line) for line in lines])
    assert {"flet", "flet-cli", "flet-notifications", "flet-secure-storage"} <= set(
        versions
    )
    pins = set().union(
        *(pin for name, pin in versions.items() if name not in from_a_flet_checkout())
    )
    assert len(pins) <= 1 and "" not in pins, versions


def test_uv_lock_holds_the_family_at_that_version() -> None:
    """`uv.lock` resolves every Flet package to the version `pyproject.toml` pins."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    wanted = family_versions(bundled_requirements())["flet"]
    for package in lock["package"]:
        name = package["name"]
        if is_flet(name) and name not in from_a_flet_checkout():
            assert {package.get("version")} == wanted, name
