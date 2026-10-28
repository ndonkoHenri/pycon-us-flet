"""The Developer screen's Data section fixtures and lookups, for its two test modules (#312).

``test_developer_data.py`` (the rows, Refresh now, Clear cached feed and the words)
and ``test_developer_data_reset.py`` (Share log, Show welcome again and Reset app) run ``DataActions`` outside a renderer, as ``Developer`` runs in
``test_developer.py``: its hooks are replaced and a fake page is bound. The feed fetch is
replaced too, so no test reaches the network. A module takes the fixtures by assigning
them to its own names, as ``docs/testing-and-quality.md`` §3.1 says.
"""

import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us import prefs as prefs_module
from pycon_us.account import Account
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import developer_data
from pycon_us.screens.developer_data import (
    DataActions,
)
from pycon_us.services import Services, api, errors
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from tests.fake_page import FakePage, bound
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPaths,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
)

DEV_FEED = "http://127.0.0.1:8000/conference-2026.json"


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Each test starts on real time, without error details, and leaves them so."""
    clock.start_fake_clock(None)
    errors.show_details(False)
    yield
    clock.start_fake_clock(None)
    errors.show_details(False)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """No test reaches the network: every fetch finds no answer. Returns the URLs asked."""
    asked: list[str] = []

    async def fetch(url: str, **_: Any) -> bytes:
        asked.append(url)
        raise api.NetworkError("ConnectError: offline")

    monkeypatch.setattr(api, "fetch_feed", fetch)
    return asked


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A fake page, bound as the session's page until the test ends."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The 2026 services over in-memory fakes and a temporary directory."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
        share=MemoryShare(),
        paths=MemoryPaths(),
    )


@pytest.fixture
def stored(svc: Services) -> dict[str, Any]:
    """What SharedPreferences holds, as the fake keeps it."""
    return cast(MemoryPrefs, svc.storage.prefs).values


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Loaded preferences with Developer unlocked, as in a packaged build."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    return Prefs(dev={"unlocked": True}, loaded=True)


@pytest.fixture
async def conference(svc: Services) -> Conference:
    """A Conference store that has published the bundled 2026 snapshot."""
    store = Conference()
    await store.load_local(svc.storage, svc.year)  # the bundled snapshot
    return store


@pytest.fixture
def favorites() -> Favorites:
    """Three saved sessions, loaded."""
    return Favorites(ids=frozenset({"1", "2", "3"}), loaded=True)


@pytest.fixture
def account() -> Account:
    """A signed-out account, restored."""
    return Account(restored=True)


@pytest.fixture
def packaged(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Make the section see a packaged build, or not."""

    def set_packaged(on: bool) -> None:
        monkeypatch.setattr(developer_data, "is_embedded", lambda: on)

    set_packaged(True)
    return set_packaged


class Rendered:
    """``DataActions`` rendered by hand: its state, the dialog it portals, its controls."""

    def __init__(self) -> None:
        """Start with no state values and no dialog shown."""
        self.values: list[Any] = []
        self.index = 0
        self.dialogs: list[ft.DialogControl | None] = []

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        """Answer ``ft.use_state`` by call order, as Flet's renderer does."""
        if self.index == len(self.values):
            self.values.append(initial() if callable(initial) else initial)
        index = self.index
        self.index += 1

        def set_value(value: Any) -> None:
            self.values[index] = value

        return self.values[index], set_value

    @property
    def dialog(self) -> ft.AlertDialog | None:
        """The confirmation the last render showed, or None."""
        last = self.dialogs[-1]
        assert last is None or isinstance(last, ft.AlertDialog)
        return last


@pytest.fixture
def rendered() -> Rendered:
    """A fresh hand renderer for ``DataActions``."""
    return Rendered()


@pytest.fixture
def minutes() -> list[int]:
    """The ``use_minute()`` calls: one per render."""
    return []


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    rendered: Rendered,
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    account: Account,
    packaged: Callable[[bool], None],
    page: FakePage,
    minutes: list[int],
) -> Callable[[], ft.Column]:
    """Render ``DataActions`` and return its column."""
    monkeypatch.setattr(ft, "use_state", rendered.use_state)
    monkeypatch.setattr(ft, "use_dialog", rendered.dialogs.append)
    monkeypatch.setattr(developer_data, "use_services", lambda: svc)
    monkeypatch.setattr(developer_data, "use_conference", lambda: conference)
    monkeypatch.setattr(developer_data, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer_data, "use_favorites", lambda: favorites)
    monkeypatch.setattr(developer_data, "use_account", lambda: account)
    monkeypatch.setattr(developer_data, "use_tokens", lambda: LIGHT_TOKENS)
    # The minute tick needs a renderer; its own tests are test_status_strip_ticks.py's.
    monkeypatch.setattr(developer_data, "use_minute", lambda: minutes.append(0) or 0)

    def render() -> ft.Column:
        rendered.index = 0
        column = inspect.unwrap(DataActions)()
        assert isinstance(column, ft.Column)
        return column

    return render


def identified(root: ft.Control) -> dict[str, ft.Control]:
    """The control under each identifier below ``root``."""
    found: dict[str, ft.Control] = {}

    def visit(control: Any) -> None:
        if isinstance(control, ft.Semantics) and control.identifier:
            found[control.identifier] = cast(ft.Control, control.content)
        for name in ("content", "controls", "actions"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(root)
    return found


def row(column: ft.Column, identifier: str) -> ft.ListTile:
    """The list tile under ``identifier`` in the column."""
    tile = identified(column)[identifier]
    assert isinstance(tile, ft.ListTile)
    return tile


def subtitle(column: ft.Column, identifier: str) -> str:
    """The subtitle's words of the row under ``identifier``."""
    return str(cast(ft.Text, row(column, identifier).subtitle).value)


async def tap(render: Callable[[], ft.Column], identifier: str) -> None:
    """Tap a row as Flutter would: a no-argument handler, maybe a coroutine."""
    result = cast(Callable[[], Any], row(render(), identifier).on_click)()
    if inspect.isawaitable(result):
        await result


async def press(dialog: ft.AlertDialog | None, identifier: str) -> None:
    """Press a confirmation's button."""
    assert dialog is not None
    button = identified(dialog)[identifier]
    assert isinstance(button, ft.TextButton)
    result = cast(Callable[[], Any], button.on_click)()
    if inspect.isawaitable(result):
        await result


def outcome(column: ft.Column) -> str | None:
    """The words of the line under the rows, or None while it is hidden."""
    line = next(
        c
        for c in column.controls
        if isinstance(c, ft.Semantics) and c.identifier == "developer.data_outcome"
    )
    assert line.live_region is True
    if not line.visible:
        return None
    text = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    assert isinstance(text, ft.Text)
    return str(text.value)


def said(page: FakePage) -> list[str]:
    """The words of every SnackBar the page has shown, in order."""
    return [
        str(cast(ft.Text, d.content).value)
        for d in page.dialogs
        if isinstance(d, ft.SnackBar)
    ]
