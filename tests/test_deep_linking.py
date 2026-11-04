"""Guard D-269: Android and iOS builds register the app's link scheme and host.

Flet's build template registers a link once `scheme` resolves, but our links are
`<scheme>://<host>/<route path>` (D-269), so these tests want both: they run flet-cli's own
resolver at the pin over `pyproject.toml`, as `flet build` does.
"""

import re
import tomllib
from argparse import Namespace
from pathlib import Path
from typing import NoReturn

import pytest
from flet_cli.commands.build_base import BaseBuildCommand
from flet_cli.utils.pyproject_toml import load_pyproject_toml

ROOT = Path(__file__).resolve().parents[1]
# flet-cli's package_platform for apk and aab, and for ipa and ios-simulator.
PLATFORMS = ("Android", "iOS")

# RFC 3986's scheme, lowercase only: Android matches an intent filter's scheme case-sensitively.
SCHEME = re.compile(r"[a-z][a-z0-9+.-]*")
HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
HOST = re.compile(rf"{HOST_LABEL}(?:\.{HOST_LABEL})*")
# A browser or the file system would claim these links before the app could.
TAKEN_SCHEMES = {"http", "https", "file"}


class Resolver(BaseBuildCommand):
    """flet-cli's build command for its resolver alone, whose stop becomes an error to read."""

    def cleanup(
        self, exit_code: int, message: object = None, no_border: bool = False
    ) -> NoReturn:
        """Raise what flet-cli would stop the build with, instead of ending the test."""
        raise ValueError(message)


def resolve(project_dir: Path, platform: str) -> tuple[object, object]:
    """Return the `(scheme, host)` that `flet build` would use for `platform`.

    Args:
        project_dir: The folder whose `pyproject.toml` is read.
        platform: flet-cli's package platform, `"Android"` or `"iOS"`.

    Returns:
        The resolved scheme and host, each `None` when it is not configured.

    Raises:
        ValueError: flet-cli would stop the build, as for a host with no scheme.
    """
    # No parser and no __init__: only the resolver runs, as flet-cli's own tests do.
    command = Resolver.__new__(Resolver)
    command.get_pyproject = load_pyproject_toml(project_dir)
    command.package_platform = platform
    command.options = Namespace(deep_linking_scheme=None, deep_linking_host=None)
    link = command.get_deep_linking()
    return link["scheme"], link["host"]


def link_problems(project_dir: Path) -> list[str]:
    """Say, per platform, what keeps a build of `project_dir` from registering its links.

    Args:
        project_dir: The folder whose `pyproject.toml` is read.

    Returns:
        One message per problem; an empty list when both platforms register a valid link.
    """
    problems = []
    for platform in PLATFORMS:
        try:
            scheme, host = resolve(project_dir, platform)
        except ValueError as stop:
            problems.append(f"{platform}: scheme: flet build stops: {stop}")
            continue
        if not (isinstance(scheme, str) and SCHEME.fullmatch(scheme)):
            problems.append(f"{platform}: scheme {scheme!r} is no lowercase URL scheme")
        elif scheme in TAKEN_SCHEMES:
            problems.append(f"{platform}: scheme {scheme!r} is the browser's or files'")
        if not (isinstance(host, str) and HOST.fullmatch(host)):
            problems.append(f"{platform}: host {host!r} is no lowercase host name")
    return problems


def write_pyproject(folder: Path, table: str) -> Path:
    """Write a `pyproject.toml` holding only `table` into `folder` and return the folder."""
    (folder / "pyproject.toml").write_text(table, encoding="utf-8")
    return folder


def test_both_platforms_register_the_link() -> None:
    """Our `pyproject.toml` resolves a valid scheme and host for Android and for iOS."""
    assert link_problems(ROOT) == []


def test_the_link_values_live_in_one_table() -> None:
    """The scheme and host are set once, in `[tool.flet.deep_linking]`, for #15 to swap."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    flet = pyproject["tool"]["flet"]
    assert set(flet["deep_linking"]) == {"scheme", "host"}
    assert "deep_linking" not in flet.get("android", {})
    assert "deep_linking" not in flet.get("ios", {})


@pytest.mark.parametrize(
    ("table", "missing"),
    [
        ('[tool.flet.deep_linking]\nhost = "app"\n', "scheme"),
        ('[tool.flet.deep_linking]\nscheme = "confcompanion"\n', "host"),
        ("[tool.flet]\n", "scheme"),
    ],
)
def test_a_missing_key_is_reported(tmp_path: Path, table: str, missing: str) -> None:
    """Removing the scheme or the host fails the check on both platforms."""
    problems = link_problems(write_pyproject(tmp_path, table))
    for platform in PLATFORMS:
        assert any(p.startswith(f"{platform}: {missing}") for p in problems)


@pytest.mark.parametrize("scheme", ["https", "http", "file", "PyconUS", "1a", "py con"])
def test_a_scheme_the_app_cannot_own_is_reported(tmp_path: Path, scheme: str) -> None:
    """A web or file scheme, an uppercase letter or an invalid character fails the check."""
    table = f'[tool.flet.deep_linking]\nscheme = "{scheme}"\nhost = "app"\n'
    problems = link_problems(write_pyproject(tmp_path, table))
    assert len(problems) == len(PLATFORMS)


@pytest.mark.parametrize("host", ["", "App", "app/now", "-app"])
def test_an_invalid_host_is_reported(tmp_path: Path, host: str) -> None:
    """An empty, uppercase or malformed host fails the check."""
    table = f'[tool.flet.deep_linking]\nscheme = "confcompanion"\nhost = "{host}"\n'
    problems = link_problems(write_pyproject(tmp_path, table))
    assert len(problems) == len(PLATFORMS)


def test_a_platform_table_overrides_the_common_one(tmp_path: Path) -> None:
    """A per-platform key wins over the common table, so the check reads what each build uses."""
    table = (
        '[tool.flet.deep_linking]\nscheme = "confcompanion"\nhost = "app"\n'
        '[tool.flet.ios.deep_linking]\nscheme = "https"\n'
    )
    assert link_problems(write_pyproject(tmp_path, table)) == [
        "iOS: scheme 'https' is the browser's or files'"
    ]
