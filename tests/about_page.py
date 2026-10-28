"""About this app's fakes, fixtures and lookups, for its three test modules (#312).

``test_about_app.py`` (the build and the 7-tap unlock), ``test_about_app_links.py`` (the
links and the Conference data section) and ``test_about_app_help.py`` (Help us fix it)
run ``AboutApp``, ``ConferenceData`` and ``HelpUsFixIt`` outside a renderer: their hooks
and ``AppScaffold`` are replaced, an external link row's body runs inline, and a fake
page is bound as Flet binds a session's page. ``test_help_report.py`` reuses the help
section's stand-ins. A module takes the fixtures by assigning them to its own names, as
``docs/testing-and-quality.md`` §3.1 says.
"""

import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.components.hooks.use_ref import MutableRef

from pycon_us import clock
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import about_app
from pycon_us.screens.about_app import AboutApp
from pycon_us.services import Services, api, errors
from pycon_us.services.build import known_build
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.ui import rows as rows_module
from pycon_us.ui import share as share_module
from tests.fake_page import FakePage, bound, phone_margin
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPaths,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
)

CONFERENCE_DATA = ft.Container()
"""What ``ConferenceData`` renders as in the page's tests: its own tests are below."""

HELP_US_FIX_IT = ft.Container()
"""What ``HelpUsFixIt`` renders as in the page's tests: its own tests are below."""


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Each test starts on real time and leaves it so."""
    clock.start_fake_clock(None)
    yield
    clock.start_fake_clock(None)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches the network: every fetch finds no answer."""

    async def fetch(url: str, **_: Any) -> bytes:
        raise api.NetworkError("ConnectError: offline")

    monkeypatch.setattr(api, "fetch_feed", fetch)


@pytest.fixture
def page() -> Iterator[FakePage]:
    """Yield a ``FakePage`` bound as the page Flet's handlers see."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The 2026 ``Services`` over in-memory prefs and device services."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
        share=MemoryShare(),
        paths=MemoryPaths(),
    )


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Fresh ``Prefs`` as in a packaged build: Developer locked, error details off."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    monkeypatch.setattr(errors, "_details", False)
    return Prefs()


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs, page: FakePage
) -> Callable[[], dict[str, Any]]:
    """Render ``AboutApp`` and return what it passed to ``AppScaffold``.

    The tap count is one ref, and the unsaved flag one state, that live as long as the
    page, as Flet's do. The build is what is known without asking (``known_build()``):
    ``use_build()``'s own tests are ``test_build.py``'s.
    """
    ref = MutableRef(0)
    unsaved: list[bool] = [False]  # the one use_state: whether the unlock was saved

    def use_state(initial: bool) -> tuple[bool, Callable[[bool], None]]:
        return unsaved[0], lambda value: unsaved.__setitem__(0, value)

    monkeypatch.setattr(ft, "use_ref", lambda initial=None: ref)
    monkeypatch.setattr(ft, "use_state", use_state)
    monkeypatch.setattr(about_app, "use_services", lambda: svc)
    monkeypatch.setattr(about_app, "use_prefs", lambda: prefs)
    monkeypatch.setattr(about_app, "use_build", known_build)
    monkeypatch.setattr(about_app, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(about_app, "use_margin", phone_margin)
    monkeypatch.setattr(about_app, "ConferenceData", lambda: CONFERENCE_DATA)
    monkeypatch.setattr(about_app, "HelpUsFixIt", lambda: HELP_US_FIX_IT)
    monkeypatch.setattr(
        rows_module, "_ExternalLinkTile", inspect.unwrap(rows_module._ExternalLinkTile)
    )
    monkeypatch.setattr(rows_module, "use_services", lambda: svc)
    return lambda: cast(dict[str, Any], inspect.unwrap(AboutApp)())


def body_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    """The page's list: its rows and headings, in order."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return body.controls


def tiles(scaffold: dict[str, Any]) -> dict[str, ft.ListTile]:
    """The build's rows by title, the version row's ``ListTile`` included."""
    found = {}
    for row in body_of(scaffold):
        if isinstance(row, ft.Semantics) and row.live_region:
            continue  # the Developer row, below
        if isinstance(row, ft.MergeSemantics):
            assert isinstance(row.content, ft.Semantics)
            if row.content.link:
                continue  # the Links section's rows, below
            row = row.content.content
        if isinstance(row, ft.ListTile):
            found[str(row.title)] = row
    return found


def headings(controls: list[ft.Control]) -> list[tuple[str, int | None]]:
    """The section headings among ``controls``: each one's text and level, in order."""
    found = []
    for control in controls:
        if isinstance(control, ft.Semantics) and control.header:
            box = control.content
            assert isinstance(box, ft.Container) and isinstance(box.content, ft.Text)
            found.append((str(box.content.value), control.heading_level))
    return found


def link_rows(scaffold: dict[str, Any]) -> dict[str, ft.Semantics]:
    """The Links section's rows by identifier: each one's link node."""
    found = {}
    for row in body_of(scaffold):
        node = row.content if isinstance(row, ft.MergeSemantics) else None
        if isinstance(node, ft.Semantics) and node.link:
            found[str(node.identifier)] = node
    return found


async def tap_version(render: Callable[[], dict[str, Any]], times: int) -> None:
    """Tap the Version row ``times`` times, rendering the page before each."""
    for _ in range(times):
        await cast(Any, tiles(render())["Version"].on_click)()


@pytest.fixture
async def conference(svc: Services) -> Conference:
    """A Conference store that has published the bundled 2026 snapshot, as offline."""
    store = Conference()
    await store.load_local(svc.storage, svc.year)
    return store


class States:
    """``ft.use_state`` answered by call order, as Flet's renderer does, across renders."""

    def __init__(self) -> None:
        """Start with no state values."""
        self.values: list[Any] = []
        self.index = 0

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        """Return the value at this call's place and its setter, made on first use."""
        if self.index == len(self.values):
            self.values.append(initial() if callable(initial) else initial)
        index = self.index
        self.index += 1
        return self.values[index], lambda value: self.values.__setitem__(index, value)


def answer_report_hooks(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    conference: Conference,
    prefs: Prefs,
) -> None:
    """Answer ``use_problem_report()``'s hooks, as in a packaged build with no saves.

    Shared with Help & safety's tests, whose Report a problem row uses the same hook.
    """
    monkeypatch.setattr(share_module, "use_services", lambda: svc)
    monkeypatch.setattr(share_module, "use_conference", lambda: conference)
    monkeypatch.setattr(share_module, "use_prefs", lambda: prefs)
    monkeypatch.setattr(share_module, "use_favorites", lambda: Favorites(loaded=True))
    monkeypatch.setattr(share_module, "is_embedded", lambda: True)


def identified(controls: list[ft.Control]) -> dict[str, ft.Semantics]:
    """The identified nodes among ``controls``, merged rows' included, by identifier."""
    found = {}
    for control in controls:
        node = control.content if isinstance(control, ft.MergeSemantics) else control
        if isinstance(node, ft.Semantics) and node.identifier:
            found[node.identifier] = node
    return found


def text_of(value: Any) -> str:
    """The words of a tile's title or subtitle, a ``Text`` or a string."""
    return str(value.value if isinstance(value, ft.Text) else value)
