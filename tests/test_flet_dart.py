"""Tests for `tests/flet_dart.py`: where a build left Flet's Dart source (D-479)."""

import json
from pathlib import Path

import pytest

from tests.flet_dart import flet_dart_file

THEME = "lib/src/utils/theme.dart"


def write_config(tmp_path: Path, root_uri: str) -> Path:
    """Write a `package_config.json` with Flet's package at `root_uri`, and return its path."""
    config = tmp_path / "build" / "package_config.json"
    config.parent.mkdir()
    packages = [
        {"name": "other", "rootUri": "../other"},
        {"name": "flet", "rootUri": root_uri},
    ]
    config.write_text(json.dumps({"packages": packages}), encoding="utf-8")
    return config


def test_finds_the_file_where_pub_put_the_package(tmp_path: Path) -> None:
    """An absolute `rootUri`, as pub writes for a git package, leads to the file."""
    wanted = tmp_path / "git" / "flet-abc" / "packages" / "flet" / THEME
    wanted.parent.mkdir(parents=True)
    wanted.write_text("// Dart\n", encoding="utf-8")
    config = write_config(tmp_path, wanted.parents[3].as_uri())
    assert flet_dart_file(THEME, config) == wanted


def test_finds_the_file_through_a_relative_root(tmp_path: Path) -> None:
    """A relative `rootUri` resolves against the config's folder."""
    wanted = tmp_path / "flet" / THEME
    wanted.parent.mkdir(parents=True)
    wanted.write_text("// Dart\n", encoding="utf-8")
    config = write_config(tmp_path, "../flet")
    assert flet_dart_file(THEME, config).resolve() == wanted.resolve()


def test_skips_where_no_build_has_run(tmp_path: Path) -> None:
    """No `package_config.json` skips the test that asked, rather than failing it."""
    with pytest.raises(pytest.skip.Exception):
        flet_dart_file(THEME, tmp_path / "missing.json")


def test_skips_when_the_file_is_not_in_the_package(tmp_path: Path) -> None:
    """A config whose package lacks the file skips too: a bump's check names what it needs."""
    config = write_config(tmp_path, (tmp_path / "flet").as_uri())
    with pytest.raises(pytest.skip.Exception):
        flet_dart_file(THEME, config)
