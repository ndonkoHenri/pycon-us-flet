"""Tests for the capability constants (D-63).

The constants are computed at import, so each case reloads the module under its own
patches, and the fixture reloads it once more afterwards, under the real environment.
"""

import importlib
import importlib.util
from collections.abc import Iterator
from importlib.machinery import ModuleSpec

import pytest

from pycon_us import capabilities

CONSTANTS = ("SECURE_STORAGE", "PERMISSIONS", "REMINDERS", "SCANNER")


@pytest.fixture
def reload_after() -> Iterator[None]:
    """Reload ``capabilities`` after the test, under the real environment."""
    yield
    importlib.reload(capabilities)


def any_spec(name: str, *args: object) -> ModuleSpec:
    """A ``find_spec`` stand-in that finds every module, whatever its name."""
    return ModuleSpec(name, None)


def test_nothing_is_available_when_not_embedded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside a packaged build, no module is available, even one that is found."""
    monkeypatch.setattr(capabilities, "is_embedded", lambda: False)
    monkeypatch.setattr(capabilities, "find_spec", any_spec)
    assert not capabilities.available("flet_secure_storage")
    assert not capabilities.available("json")


def test_a_bundled_module_is_available_in_a_packaged_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In a packaged build, a module the build can import is available; no other is."""
    monkeypatch.setattr(capabilities, "is_embedded", lambda: True)
    assert capabilities.available("json")
    assert not capabilities.available("no_such_module_in_this_build")


def test_every_capability_is_off_in_the_companion_app(reload_after: None) -> None:
    """Without ``FLET_PLATFORM``, every constant is False, all extensions found.

    ``flet run`` and the companion app never set ``FLET_PLATFORM`` (F14).
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("FLET_PLATFORM", raising=False)
        patch.setattr(importlib.util, "find_spec", any_spec)
        importlib.reload(capabilities)
        assert {
            name: getattr(capabilities, name) for name in CONSTANTS
        } == dict.fromkeys(CONSTANTS, False)


def test_every_capability_follows_its_bundled_extension(reload_after: None) -> None:
    """In a packaged build, every constant is True with its module found, else False."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("FLET_PLATFORM", "android")
        patch.setattr(importlib.util, "find_spec", any_spec)
        importlib.reload(capabilities)
        assert all(getattr(capabilities, name) for name in CONSTANTS)

        patch.setattr(importlib.util, "find_spec", lambda name, *args: None)
        importlib.reload(capabilities)
        assert not any(getattr(capabilities, name) for name in CONSTANTS)


def test_the_test_run_itself_is_not_embedded() -> None:
    """Imported by pytest, outside a packaged build, every constant is False."""
    assert not any(getattr(capabilities, name) for name in CONSTANTS)
