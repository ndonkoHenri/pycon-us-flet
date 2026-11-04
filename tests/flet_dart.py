"""Find Flet's Dart source for the tests that mirror it.

No wheel carries it: `flet build` gets the Dart package through pub, so it's on disk only where a
build of our Flet has run. These tests skip elsewhere, and a Flet bump runs them after its build
(`docs/development.md` §2.2).
"""

import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

import pytest
from flet.version import flet_version

BUILD = Path(__file__).resolve().parents[1] / "build"


def flet_dart_file(
    relative: str, build: Path = BUILD, version: str = flet_version
) -> Path:
    """Return a file of Flet's Dart package from a build of our Flet, or skip the test.

    A build of another version is skipped, so a bump can't pass on the old source. Once the
    build is ours, a missing file fails: Flet has moved what the test mirrors.

    Args:
        relative: The file's path inside `packages/flet`.
        build: The `build` folder.
        version: The Flet version the build must be of.

    Returns:
        The file's path.
    """
    config = build / "flutter/.dart_tool/package_config.json"
    built_ours = any(build.glob(f"site-packages/*/flet-{version}.dist-info"))
    if not built_ours or not config.exists():
        pytest.skip(
            f"needs a build of Flet {version} here, for its Dart source ({relative})"
        )
    packages = json.loads(config.read_text(encoding="utf-8"))["packages"]
    root_uri = next(
        package["rootUri"] for package in packages if package["name"] == "flet"
    )
    root = urljoin(config.as_uri(), root_uri)
    found = Path(url2pathname(urlsplit(root).path)) / relative
    assert found.exists(), f"Flet {version} has no {relative}: update what mirrors it"
    return found
