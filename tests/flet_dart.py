"""Find Flet's Dart source for the tests that mirror it.

No wheel carries it: `flet build` gets the Dart package through pub, so it's on disk only where a
build has run. These tests skip elsewhere, and a Flet bump runs them after its build
(`docs/development.md` §2.2).
"""

import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

import pytest

PACKAGE_CONFIG = (
    Path(__file__).resolve().parents[1] / "build/flutter/.dart_tool/package_config.json"
)


def flet_dart_file(relative: str, config: Path = PACKAGE_CONFIG) -> Path:
    """Return a file of Flet's Dart package as the last build resolved it, or skip the test.

    Args:
        relative: The file's path inside `packages/flet`.
        config: The build's `package_config.json`, which says where pub put each package.

    Returns:
        The file's path.
    """
    if config.exists():
        packages = json.loads(config.read_text(encoding="utf-8"))["packages"]
        for package in packages:
            if package["name"] == "flet":
                root = urljoin(config.as_uri(), package["rootUri"])
                found = Path(url2pathname(urlsplit(root).path)) / relative
                if found.exists():
                    return found
    pytest.skip(f"needs a build here for Flet's Dart source ({relative})")
