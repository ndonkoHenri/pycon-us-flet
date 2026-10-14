"""The fixtures and lookups of the shared chrome's tests, outside a renderer (#264).

- The services, the page and the ``Conference`` store (``year``, ``svc``, ``page``,
  ``conference``): for ``AppScaffold``'s tests and the status strip's
  (``tests/strip.py`` has the strip's own ``hooks``).
- ``AppScaffold``'s ``hooks`` and lookups, for ``test_scaffold.py`` (the app bar, Back
  and the body), ``test_shown.py`` (``Shown`` and the content line) and
  ``test_navigation.py`` (the bottom bar on a View): the hooks ``AppScaffold`` calls
  (``ft.use_view_path``, ``ft.use_effect`` and the store hooks) are answered by
  ``Hooks``, and a fake page is bound as Flet binds a session's page.

A test module takes the fixtures by assigning them to its own names, which is where
pytest looks a fixture up: ``year, svc, page, conference, hooks = (chrome.year,
...)``. An import would do the same, but ruff reads an imported fixture as unused and
each test's parameter as its redefinition (F401, F811). A fixture finds the fixtures
it takes the same way, by name in the test's module: both families' ``hooks`` take
``svc`` (which takes ``year``) and ``conference``, so a module that assigns a ``hooks``
assigns those three too, or pytest stops with "fixture 'svc' not found".
"""

import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.ui import scaffold
from pycon_us.ui.scaffold import AppScaffold, Shown
from tests.fakes import (
    FakePage,
    Hooks,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)


@pytest.fixture(scope="module")
def year() -> YearData:
    """The 2026 year data, loaded once per module."""
    return load_year(2026)


@pytest.fixture
def svc(year: YearData, tmp_path: Path) -> Services:
    """The services with the memory fakes, storing under the test's ``tmp_path``."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=year,
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A fake page, bound as Flet binds a session's page."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def conference() -> Conference:
    """An empty ``Conference`` store."""
    return Conference()


@pytest.fixture
def hooks(
    monkeypatch: pytest.MonkeyPatch, svc: Services, conference: Conference
) -> Hooks:
    """Answer ``AppScaffold``'s hooks, and run ``Shown``'s body inline."""
    hooks = Hooks()
    monkeypatch.setattr(ft, "use_view_path", lambda: hooks.view_path)
    monkeypatch.setattr(ft, "use_effect", hooks.use_effect)
    monkeypatch.setattr(scaffold, "use_services", lambda: svc)
    monkeypatch.setattr(scaffold, "use_conference", lambda: conference)
    # ``Shown``'s body runs inline: no renderer here.
    monkeypatch.setattr(scaffold, "Shown", inspect.unwrap(Shown))
    # The probe reads Prefs; its own tests are in test_time_gutter.py.
    monkeypatch.setattr(scaffold, "GutterProbe", Probe)
    return hooks


def Probe() -> ft.Control:
    """``GutterProbe``'s stand-in: a control the tests can find."""
    return ft.Container(key="probe")


def body_of(view: ft.View) -> ft.Control:
    """The body the screen gave, in the SafeArea above the gutter probe."""
    safe, _ = view.controls
    assert isinstance(safe, ft.SafeArea)
    assert safe.content is not None
    return safe.content


def view_at(hooks: Hooks, page: FakePage, view_path: str, **kwargs: Any) -> ft.View:
    """Build the View of view_path while page.route addresses it (the top View)."""
    hooks.view_path = view_path
    page.route = page.route if kwargs.pop("below", False) else view_path
    kwargs.setdefault("title", "Title")
    return AppScaffold(body=ft.Text("body"), **kwargs)


def app_bar(view: ft.View) -> ft.AppBar:
    """The View's Material app bar."""
    assert isinstance(view.appbar, ft.AppBar)
    return view.appbar


def click(button: ft.IconButton) -> None:
    """Call a button's handler as Flet does: without the event when it takes none."""
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()


def merged_button(control: ft.Control | None) -> ft.IconButton:
    """Return the icon button that ``merged()`` made one node with its tooltip (F55)."""
    assert isinstance(control, ft.MergeSemantics)
    button = control.content
    assert isinstance(button, ft.IconButton)
    return button


def back_arrow(view: ft.View) -> ft.IconButton:
    """The app bar's Back arrow, which a pushed View has."""
    return merged_button(app_bar(view).leading)
