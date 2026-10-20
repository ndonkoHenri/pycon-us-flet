"""Tests for Settings: Appearance and its High contrast switch (#421; THEME-01, D-286).

``Settings`` runs outside a renderer, as ``More`` does in ``test_more.py``: its hooks and
``AppScaffold`` are replaced, and a fake page is bound as Flet binds a session's page.
That the theme follows ``Prefs`` is ``test_app.py``'s; how the page looks and reads is
checked on devices (the PR).
"""

import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.locations import PAGES, parent_of
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import settings
from pycon_us.screens.settings import FOLLOWS_DEVICE, RADIO_WIDTH, Settings
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)


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
def prefs() -> Prefs:
    """Prefs at their defaults, as on a first launch: both settings follow the OS."""
    return Prefs()


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, svc: Services, prefs: Prefs, page: FakePage
) -> Callable[[], dict[str, Any]]:
    """Render ``Settings`` once and return what it passed to ``AppScaffold``.

    The services come first: a service built while a page is bound registers with it.
    """
    monkeypatch.setattr(settings, "use_services", lambda: svc)
    monkeypatch.setattr(settings, "use_prefs", lambda: prefs)
    monkeypatch.setattr(settings, "AppScaffold", lambda **kwargs: kwargs)

    def render() -> dict[str, Any]:
        return cast(dict[str, Any], inspect.unwrap(Settings)())

    return render


def rows_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    """Return the rows of the scaffold's ``ListView`` body."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return list(body.controls)


def appearance_of(scaffold: dict[str, Any]) -> ft.RadioGroup:
    """Return Appearance's ``RadioGroup``, the row under its heading."""
    choice = rows_of(scaffold)[1]
    assert isinstance(choice, ft.RadioGroup)
    return choice


def options_of(choice: ft.RadioGroup) -> list[tuple[str | None, str, ft.ListTile]]:
    """Each option row as (identifier, its radio's value, its tile)."""
    column = choice.content
    assert isinstance(column, ft.Column)
    options = []
    for row in column.controls:
        assert isinstance(row, ft.MergeSemantics)  # one node per option
        assert isinstance(row.content, ft.Semantics)
        tile = row.content.content
        assert isinstance(tile, ft.ListTile) and isinstance(tile.leading, ft.Radio)
        options.append((row.content.identifier, str(tile.leading.value), tile))
    return options


def contrast_row_of(scaffold: dict[str, Any]) -> tuple[ft.Semantics, ft.ListTile]:
    """Return the High contrast row's identifier node and its tile."""
    row = rows_of(scaffold)[2]
    assert isinstance(row, ft.MergeSemantics)  # one node (D-214)
    node = row.content
    assert isinstance(node, ft.Semantics)
    assert isinstance(node.content, ft.ListTile)
    return node, node.content


def switch_of(scaffold: dict[str, Any]) -> ft.Switch:
    """Return the High contrast row's switch."""
    _, tile = contrast_row_of(scaffold)
    assert isinstance(tile.trailing, ft.Switch)
    return tile.trailing


async def choose(choice: ft.RadioGroup, value: str) -> None:
    """Pick an option as Flutter reports it: the value first, then ``on_change``."""
    choice.value = value
    await cast(Any, choice.on_change)(SimpleNamespace(control=choice))


async def flip(switch: ft.Switch) -> None:
    """Toggle the switch as Flutter reports it: the new value first, then ``on_change``."""
    switch.value = not switch.value
    await cast(Any, switch.on_change)(SimpleNamespace(control=switch))


async def relaunched(svc: Services) -> Prefs:
    """Return the settings a new launch reads from the same storage."""
    fresh = Prefs()
    await fresh.load(svc.storage)
    return fresh


def snack_texts(page: FakePage) -> list[str | None]:
    """The texts of the SnackBars the page has shown, each floating (D-29)."""
    texts = []
    for snack in page.dialogs:
        assert isinstance(snack, ft.SnackBar)
        assert snack.behavior == ft.SnackBarBehavior.FLOATING
        assert isinstance(snack.content, ft.Text)
        texts.append(snack.content.value)
    return texts


def test_settings_is_a_page_under_more_so_back_returns_there() -> None:
    """``/more/settings`` is a page whose parent is More: one pushed View (D-17)."""
    assert "/more/settings" in PAGES
    assert parent_of("/more/settings") == "/more"


def test_the_page_is_titled_and_opens_with_appearance_as_a_section_heading(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The page is "Settings", and "Appearance" is a level-2 heading over its rows."""
    scaffold = render()
    assert scaffold["title"] == "Settings"  # level 1, the bar's title (D-211)
    heading = rows_of(scaffold)[0]
    assert isinstance(heading, ft.Semantics)
    assert heading.header and heading.heading_level == 2  # a section (D-211)
    assert isinstance(heading.content, ft.Container)
    assert isinstance(heading.content.content, ft.Text)
    assert heading.content.content.value == "Appearance"
    assert len(rows_of(scaffold)) == 3  # the heading, the radios, the switch row


def test_appearance_offers_three_radio_rows_whose_whole_row_selects(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Appearance offers System, Light and Dark as merged tiles whose whole row selects."""
    options = options_of(appearance_of(render()))
    assert [(ident, value, tile.title) for ident, value, tile in options] == [
        ("settings.appearance.system", "system", "System"),
        ("settings.appearance.light", "light", "Light"),
        ("settings.appearance.dark", "dark", "Dark"),
    ]
    assert all(tile.toggle_inputs for _, _, tile in options)


def test_appearance_shows_the_stored_choice(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """The radio group shows the stored theme, System on a first launch."""
    assert appearance_of(render()).value == "system"
    prefs.theme = "dark"
    assert appearance_of(render()).value == "dark"  # controlled (D-157)


async def test_choosing_an_appearance_applies_and_survives_a_relaunch(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    """Choosing Dark sets it in Prefs at once, says nothing, and a relaunch reads it."""
    await choose(appearance_of(render()), "dark")
    assert prefs.theme == "dark" and prefs.dark  # App's theme follows Prefs
    assert page.dialogs == []
    assert (await relaunched(svc)).theme == "dark"


async def test_an_appearance_that_cannot_be_saved_stays_and_says_so(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    """A choice that cannot be saved still shows, and a floating SnackBar says so."""
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await choose(appearance_of(render()), "light")
    assert prefs.theme == "light"  # applied for this session (D-120)
    assert appearance_of(render()).value == "light"
    assert snack_texts(page) == ["Couldn't save your change"]


def test_the_high_contrast_row_is_one_switch_row_named_for_flows(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The row is one merged node, ``settings.high_contrast``, that the whole row toggles."""
    node, tile = contrast_row_of(render())
    assert node.identifier == "settings.high_contrast"
    assert tile.title == "High contrast"
    assert tile.toggle_inputs  # a tap anywhere on the row toggles the switch
    slot = tile.leading
    assert isinstance(slot, ft.Container)
    assert slot.width == RADIO_WIDTH  # its title starts where Appearance's titles do
    assert slot.alignment == ft.Alignment.CENTER  # the icon sits under the radios
    assert isinstance(slot.content, ft.Icon)
    assert slot.content.icon == ft.Icons.CONTRAST_OUTLINED
    assert slot.content.semantics_label is None  # decorative: the title names it
    assert isinstance(tile.trailing, ft.Switch)


@pytest.mark.parametrize("os_flag", [False, True])
def test_under_system_the_switch_shows_the_os_flag_and_says_it_follows_it(
    render: Callable[[], dict[str, Any]], prefs: Prefs, os_flag: bool
) -> None:
    """Under "system" the switch shows the OS flag, and the subtitle says it follows it."""
    prefs.os_high_contrast = os_flag
    _, tile = contrast_row_of(render())
    assert tile.subtitle == FOLLOWS_DEVICE
    assert switch_of(render()).value is os_flag


def test_under_system_the_switch_follows_a_change_read_on_resume(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """A flag read on resume (``read_accessibility``) moves the switch under "system"."""
    assert switch_of(render()).value is False
    prefs.os_high_contrast = True  # what the resume's read writes (D-23)
    assert switch_of(render()).value is True


async def test_switching_against_the_os_holds_and_survives_a_relaunch(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    """On with the OS off stores "on": HC applies, the subtitle goes, a relaunch keeps it."""
    await flip(switch_of(render()))
    assert prefs.high_contrast == "on" and prefs.high_contrast_on  # applies at once
    assert page.dialogs == []
    _, tile = contrast_row_of(render())
    assert tile.subtitle is None
    assert switch_of(render()).value is True
    assert (await relaunched(svc)).high_contrast == "on"


async def test_switching_back_to_the_os_flag_follows_the_os_again(
    render: Callable[[], dict[str, Any]], prefs: Prefs, svc: Services
) -> None:
    """Off with the OS on stores "off"; on again stores "system", saved as such."""
    prefs.os_high_contrast = True
    await flip(switch_of(render()))
    assert prefs.high_contrast == "off" and not prefs.high_contrast_on
    await flip(switch_of(render()))
    assert prefs.high_contrast == "system" and prefs.high_contrast_on
    assert contrast_row_of(render())[1].subtitle == FOLLOWS_DEVICE
    assert (await relaunched(svc)).high_contrast == "system"


async def test_a_switch_that_cannot_be_saved_stays_and_says_so(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    """A switch that cannot be saved still applies, and a floating SnackBar says so."""
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await flip(switch_of(render()))
    assert prefs.high_contrast == "on"  # applied for this session (D-120)
    assert switch_of(render()).value is True
    assert snack_texts(page) == ["Couldn't save your change"]
    assert (await relaunched(svc)).high_contrast == "system"  # lost on relaunch
