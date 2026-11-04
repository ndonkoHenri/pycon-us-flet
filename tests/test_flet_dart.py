"""Tests for `tests/flet_dart.py`: where a build left Flet's Dart source (D-481)."""

import json
from pathlib import Path

import pytest

from tests.flet_dart import flet_dart_file

THEME = "lib/src/utils/theme.dart"


def write_build(tmp_path: Path, root_uri: str, version: str = "1.2.3") -> Path:
    """Write a `build` folder of Flet `version`, its package at `root_uri`, and return its path."""
    build = tmp_path / "build"
    (build / f"site-packages/android.arm64/flet-{version}.dist-info").mkdir(
        parents=True
    )
    config = build / "flutter/.dart_tool/package_config.json"
    config.parent.mkdir(parents=True)
    packages = [
        {"name": "other", "rootUri": "../other"},
        {"name": "flet", "rootUri": root_uri},
    ]
    config.write_text(json.dumps({"packages": packages}), encoding="utf-8")
    return build


def write_theme(root: Path) -> Path:
    """Write the theme file inside a package at `root`, and return its path."""
    theme = root / THEME
    theme.parent.mkdir(parents=True)
    theme.write_text("// Dart\n", encoding="utf-8")
    return theme


def test_finds_the_file_where_pub_put_the_package(tmp_path: Path) -> None:
    """An absolute `rootUri`, as pub writes for a git package, leads to the file."""
    root = tmp_path / "git" / "flet-abc" / "packages" / "flet"
    wanted = write_theme(root)
    build = write_build(tmp_path, root.as_uri())
    assert flet_dart_file(THEME, build, "1.2.3") == wanted


def test_finds_the_file_through_a_relative_root(tmp_path: Path) -> None:
    """A relative `rootUri` resolves against the config's folder."""
    build = write_build(tmp_path, "../pkg")
    wanted = write_theme(build / "flutter" / "pkg")
    assert flet_dart_file(THEME, build, "1.2.3").resolve() == wanted.resolve()


def test_skips_where_no_build_has_run(tmp_path: Path) -> None:
    """No `build` folder skips the test that asked, rather than failing it."""
    with pytest.raises(pytest.skip.Exception):
        flet_dart_file(THEME, tmp_path / "build", "1.2.3")


def test_skips_a_build_of_another_flet(tmp_path: Path) -> None:
    """A build left from before a bump doesn't count, even with the file in it."""
    root = tmp_path / "flet"
    write_theme(root)
    build = write_build(tmp_path, root.as_uri(), version="1.2.2")
    with pytest.raises(pytest.skip.Exception):
        flet_dart_file(THEME, build, "1.2.3")


def test_fails_when_our_flet_has_moved_the_file(tmp_path: Path) -> None:
    """In a build of our Flet, a missing file fails: skipping would hide the change."""
    build = write_build(tmp_path, (tmp_path / "flet").as_uri())
    with pytest.raises(AssertionError, match=THEME):
        flet_dart_file(THEME, build, "1.2.3")
