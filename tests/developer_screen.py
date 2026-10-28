"""The Developer screen's fixtures and lookups, for its two test modules (#88; #623).

``test_developer.py`` (the controls, the fields and the flags) and
``test_developer_apply.py`` (Apply, Reset and the pickers) run ``Developer`` outside a
renderer: its hooks and ``AppScaffold`` are replaced, and a fake page is bound as Flet
binds a session's page. A module takes the fixtures by assigning them to its own names,
as ``docs/testing-and-quality.md`` §3.1 says.
"""

import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import developer
from pycon_us.screens.developer import Developer
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from tests.fake_page import FakePage, bound, phone_margin
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
FEED = "http://127.0.0.1:8000/conference-2026.json"


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Each test starts on real time and leaves the process on it."""
    clock.start_fake_clock(None)
    yield
    clock.start_fake_clock(None)


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A ``FakePage`` bound as Flet binds a session's page."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services over in-memory fakes and a 2026 ``Storage``."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Prefs of a packaged build with Developer unlocked and nothing else set."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    return Prefs(dev={"unlocked": True})


@pytest.fixture
def conference() -> Conference:
    """An empty ``Conference`` store."""
    return Conference()


class States:
    """``ft.use_state`` for one component: the values, kept in call order."""

    def __init__(self) -> None:
        """Start with no values, at the first call's index."""
        self.values: list[Any] = []
        self.index = 0

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        """Return the value at this call's index, made from ``initial`` the first time.

        The setter writes that value in place; ``render`` resets the index first.
        """
        if self.index == len(self.values):
            self.values.append(initial() if callable(initial) else initial)
        index = self.index
        self.index += 1

        def set_value(value: Any) -> None:
            self.values[index] = value

        return self.values[index], set_value


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    page: FakePage,
) -> Callable[[], dict[str, Any]]:
    """Render ``Developer`` and return what it passed to ``AppScaffold``."""
    states = States()
    monkeypatch.setattr(ft, "use_state", states.use_state)
    monkeypatch.setattr(developer, "use_services", lambda: svc)
    monkeypatch.setattr(developer, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer, "use_conference", lambda: conference)
    monkeypatch.setattr(developer, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(developer, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(developer, "use_margin", phone_margin)
    # The Data and Mock API sections are components of their own, with their tests.
    monkeypatch.setattr(developer, "DataActions", lambda: ft.Container())
    monkeypatch.setattr(developer, "MockApiSection", lambda: ft.Container())

    def render() -> dict[str, Any]:
        states.index = 0
        return cast(dict[str, Any], inspect.unwrap(Developer)())

    return render


def by_identifier(scaffold: dict[str, Any]) -> dict[str, ft.Control]:
    """The controls under each ``developer.*`` identifier."""
    found: dict[str, ft.Control] = {}

    def visit(control: Any) -> None:
        if isinstance(control, ft.Semantics) and control.identifier:
            found[control.identifier] = cast(ft.Control, control.content)
        for name in ("content", "controls"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(scaffold["body"])
    return found


def merged_identifiers(scaffold: dict[str, Any]) -> set[str]:
    """The identifiers merged into their control's node: ``MergeSemantics(Semantics)``."""
    found: set[str] = set()

    def visit(control: Any) -> None:
        if isinstance(control, ft.MergeSemantics):
            inner = control.content
            if isinstance(inner, ft.Semantics) and inner.identifier:
                found.add(inner.identifier)
        for name in ("content", "controls", "suffix_icon"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(scaffold["body"])
    return found


def clock_picker_button(text_field: ft.TextField) -> ft.IconButton:
    """The fake-clock field's picker, merged with its identifier (D-214)."""
    merged = text_field.suffix_icon
    assert isinstance(merged, ft.MergeSemantics)
    node = merged.content
    assert isinstance(node, ft.Semantics)
    assert node.identifier == "developer.clock_picker"
    assert isinstance(node.content, ft.IconButton)
    return node.content


def field(scaffold: dict[str, Any], identifier: str) -> ft.TextField:
    """Return the ``TextField`` under ``identifier`` in a rendered scaffold."""
    control = by_identifier(scaffold)[identifier]
    assert isinstance(control, ft.TextField)
    return control


async def type_into(
    render: Callable[[], dict[str, Any]], identifier: str, text: str
) -> None:
    """Type as Flutter reports it: the field's value first, then ``on_change``."""
    text_field = field(render(), identifier)
    text_field.value = text
    cast(Callable[[object], None], text_field.on_change)(
        SimpleNamespace(control=text_field)
    )


async def press(render: Callable[[], dict[str, Any]], identifier: str) -> None:
    """Render, then click the button under ``identifier`` and await its handler."""
    button = by_identifier(render())[identifier]
    assert isinstance(button, ft.FilledButton | ft.OutlinedButton)
    await cast(Any, button.on_click)()


def outcome_row(render: Callable[[], dict[str, Any]]) -> ft.Row | None:
    """The line under the buttons, its icon and its words, or None while it is hidden."""
    line = next(
        c
        for c in cast(ft.ListView, render()["body"]).controls
        if isinstance(c, ft.Semantics) and c.identifier == "developer.outcome"
    )
    assert line.live_region is True
    if not line.visible:
        return None
    assert isinstance(line.content, ft.Container)
    assert isinstance(line.content.content, ft.Row)
    return line.content.content


def outcome(render: Callable[[], dict[str, Any]]) -> str | None:
    """The words of the line under the buttons, or None while it is hidden."""
    row = outcome_row(render)
    if row is None:
        return None
    _, text = row.controls
    assert isinstance(text, ft.Text)
    assert text.text_align == ft.TextAlign.START  # as the page's other text
    return str(text.value)


def outcome_icon(row: ft.Row) -> ft.Icon:
    """The outcome line's icon, in the slot that lines its words up with the tiles."""
    slot = row.controls[0]
    assert isinstance(slot, ft.Container) and isinstance(slot.content, ft.Icon)
    icon = slot.content
    # A ListTile's leading slot and gap at 100 %: the 20 dp icon centred in 24 dp,
    # the words starting where the tiles' do (56 dp).
    side = cast(ft.Padding, slot.padding).left
    assert (side, icon.size, row.spacing) == (2, 20, 18)
    assert icon.apply_text_scaling  # one line tall at every text size (D-373)
    return icon
