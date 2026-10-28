"""Tests for which build the app says it is: version and build number (D-386, U4).

``read_build()`` and ``use_build()`` run on a fake page; ``is_embedded()`` is switched by
hand, since nothing is embedded under pytest. About this app's row is
``test_about_app.py``'s, the diagnostics' Build line ``test_diagnostics.py``'s.
"""

import logging
from collections.abc import Iterator
from typing import cast

import flet as ft
import pytest

import pycon_us
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.services import build
from pycon_us.services.build import UNPACKAGED, Build, known_build, read_build
from pycon_us.services.diagnostics import diagnostics_text, gather_facts
from pycon_us.state import Conference
from tests.diagnostics_facts import fields
from tests.fake_page import FakePage, Hooks, bound


def package(version: str = "0.4.0", number: str = "812") -> ft.PackageInfo:
    """The package info a packaged build reports, with ``version`` and ``number``."""
    return ft.PackageInfo(
        app_name="Conf Companion",
        package_name="dev.example.confcompanion",
        version=version,
        build_number=number,
        build_signature="",
    )


@pytest.fixture(autouse=True)
def nothing_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no package info read yet."""
    monkeypatch.setattr(build, "_packaged", None)


@pytest.fixture
def packaged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run as a packaged build (``is_embedded()``)."""
    monkeypatch.setattr(build, "is_embedded", lambda: True)


@pytest.fixture
def page() -> Iterator[FakePage]:
    """Yield a ``FakePage`` that reports ``package()``, bound as Flet binds it."""
    fake = FakePage()
    fake.package = package()
    with bound(fake):
        yield fake


@pytest.mark.parametrize(
    ("given", "label"),
    [(Build("0.4.0", "812"), "0.4.0 (812)"), (Build("0.4.0"), "0.4.0")],
)
def test_the_label_puts_the_number_after_the_version(given: Build, label: str) -> None:
    """The row says "0.4.0 (812)", and the version alone without a number."""
    assert given.label == label


async def test_the_companion_says_its_own_version_and_never_asks(
    page: FakePage,
) -> None:
    """Not embedded, the app says ``__version__`` alone: the call would name the client."""
    assert await read_build(cast(ft.Page, page)) == Build(pycon_us.__version__)
    assert page.package_reads == 0


@pytest.mark.usefixtures("packaged")
async def test_a_packaged_build_asks_once_and_keeps_the_answer(page: FakePage) -> None:
    """A packaged build reads its version and number once, then says it without asking."""
    assert known_build() == UNPACKAGED  # before the answer
    assert await read_build(cast(ft.Page, page)) == Build("0.4.0", "812")
    assert await read_build(cast(ft.Page, page)) == Build("0.4.0", "812")
    assert page.package_reads == 1
    assert known_build() == Build("0.4.0", "812")


@pytest.mark.usefixtures("packaged")
async def test_a_blank_answer_falls_back_to_the_app_s_version(page: FakePage) -> None:
    """A platform that names no version or number leaves ``__version__`` alone."""
    page.package = package(version="", number="")
    assert await read_build(cast(ft.Page, page)) == Build(pycon_us.__version__)


@pytest.mark.usefixtures("packaged")
async def test_a_failed_call_says_the_version_and_asks_again_later(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    """A call that fails says ``__version__``, logs the class only, and is not kept."""
    page.package_error = TimeoutError("Timeout waiting for get_package_info")
    with caplog.at_level(logging.WARNING):
        assert await read_build(cast(ft.Page, page)) == UNPACKAGED
    assert "TimeoutError" in caplog.text and "Timeout waiting" not in caplog.text
    page.package_error = None
    assert await read_build(cast(ft.Page, page)) == Build("0.4.0", "812")


@pytest.mark.usefixtures("packaged")
async def test_the_hook_starts_with_what_is_known_then_sets_the_answer(
    monkeypatch: pytest.MonkeyPatch, page: FakePage
) -> None:
    """``use_build()`` shows the version at once, then the answer its effect reads."""
    hooks = Hooks()
    monkeypatch.setattr(ft, "use_state", hooks.use_state)
    monkeypatch.setattr(ft, "use_effect", hooks.use_effect)
    assert build.use_build() == UNPACKAGED
    [(setup, dependencies)] = hooks.effects
    assert dependencies == []  # once per mount
    await setup()
    assert hooks.state == Build("0.4.0", "812") and hooks.renders == 1


@pytest.mark.usefixtures("packaged")
async def test_the_diagnostics_name_a_packaged_build_s_version_and_number(
    page: FakePage,
) -> None:
    """A packaged build's text says its own version on App and its number on Build."""
    year = load_year(2026)
    facts = await gather_facts(
        cast(ft.Page, page),
        info=year.conference,
        conference=Conference(),
        prefs=Prefs(),
        favorites=Favorites(loaded=True),
    )
    lines = fields(diagnostics_text(facts))
    assert (lines["App"], lines["Build"]) == ("0.4.0", "812")
