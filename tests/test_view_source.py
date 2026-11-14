"""Tests for View source: the overflow item behind `SOURCE_URL` (NEW-09, #834, D-461).

The app's real Router renders every route and drill page (`tests/links.py`'s
`open_at`), so a screen's bar is the one `AppScaffold` builds: while `SOURCE_URL`
is None it holds what it held before, and once it is set exactly one overflow, whose
last item opens that screen's own module.
"""

import ast
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

import pycon_us
from pycon_us.locations import WELCOME
from pycon_us.routes import DRILL, ROUTES, UNKNOWN
from pycon_us.screens import plan, room, schedule_changes, session, speaker, sponsor
from pycon_us.screens import sprints as sprints_screen
from pycon_us.services import Services
from pycon_us.ui import menus
from pycon_us.ui.menus import (
    VIEW_SOURCE,
    source_link,
    source_menu,
    view_source_items,
)
from pycon_us.ui.session_rows import is_notice
from tests import chrome, links
from tests.chrome import app_bar, view_at
from tests.fake_page import FakePage, Hooks
from tests.fakes import MemoryLauncher
from tests.links import DATA, YEAR, Open, Shown
from tests.sessions import menu_text

open_at = links.open_at

# `AppScaffold`'s fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)

URL = "https://example.org/conf"
"""What the tests set `SOURCE_URL` to."""

ITEM = "app.view_source"
"""The item's identifier."""

TRACK_PAGE = "/more/tracks/talks"
"""A track of 2026 whose sessions can be saved, so its page has Add all."""

SESSION_PAGE = "/schedule/session/31"
"""A session of 2026 with its own overflow."""

PLAN_PAGE = "/map/plan/campus"
"""A floor plan with the floor viewer's overflow."""

CHANGES_PAGE = "/schedule/changes/2026"
"""The change log of the year on screen, with Mark all as seen."""

DRILL_PAGES = {
    SESSION_PAGE: session.__name__,
    f"/now/speaker/{next(iter(DATA.speakers))}": speaker.__name__,
    "/map/room/grand-ballroom-a": room.__name__,
    "/more/sponsors/sponsor/bloomberg": sponsor.__name__,
    PLAN_PAGE: plan.__name__,
    "/map/plan/expo": plan.__name__,
    CHANGES_PAGE: schedule_changes.__name__,
}
"""One page per drill kind: `Drill()` dispatches, so the table doesn't name them."""


def route_pages(routes: list[Any], prefix: str = "") -> Iterator[tuple[str, str]]:
    """Yield every page of `routes` with its screen's module, its params filled in.

    The index route (`Start`), Welcome and the unknown route have no View source:
    the first two have no app bar, the last no screen of ours to show.
    """
    for route in routes:
        if (
            route is DRILL
            or route is UNKNOWN
            or route.index
            or f"/{route.path}" == WELCOME
        ):
            continue
        location = f"{prefix}/{route.path}"
        filled = location.replace(":slug", "talks").replace(":licence", "python")
        yield filled, route.component.__module__
        yield from route_pages(route.children or [], location)


EVERY_PAGE = {**dict(route_pages(ROUTES)), **DRILL_PAGES}
"""Every location the settled screens answer, with the module View source opens."""

OWN_MENUS = {
    "/schedule": "schedule.overflow",
    "/map": "map.overflow",
    "/more/sprints": "sprints.menu",
    "/more/tracks/sprints": "sprints.menu",
    TRACK_PAGE: "track.menu",
    SESSION_PAGE: "session.overflow",
    PLAN_PAGE: "plan.overflow",
    CHANGES_PAGE: "changes.overflow",
}
"""The bars with an overflow of their own over the 2026 data, as before View source."""


def bar_menus(view: ft.View) -> dict[str, ft.PopupMenuButton]:
    """The View's app bar's overflow buttons, by identifier.

    An action may be a component (`SessionMenu`), so the walk goes through what it
    rendered, `_b`, as well as through `named()`'s wrappers.
    """
    found: dict[str, ft.PopupMenuButton] = {}
    for action in cast(ft.AppBar, view.appbar).actions or []:
        node: Any = action
        identifier = ""
        while node is not None and not isinstance(node, ft.PopupMenuButton):
            if isinstance(node, ft.Semantics):
                identifier = str(node.identifier)
            node = getattr(node, "_b", None) or getattr(node, "content", None)
        if node is not None:
            found[identifier] = node
    return found


def identifier_of(item: ft.PopupMenuItem) -> str | None:
    """The identifier on `menu_item()`'s item."""
    return cast(ft.Semantics, item.content).identifier


def source_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set `SOURCE_URL` where View source reads it, as the shipped build has it."""
    monkeypatch.setattr(menus, "SOURCE_URL", URL)


def link_to(module: str) -> tuple[str, ft.LaunchMode]:
    """The launch that opens `module`: at this version's tag, in the in-app browser."""
    path = module.replace(".", "/")
    url = f"{URL}/blob/v{pycon_us.__version__}/src/{path}.py"
    return (url, ft.LaunchMode.IN_APP_BROWSER_VIEW)


async def assert_one_overflow_ending_in_view_source(
    shown: Shown, identifier: str, module: str
) -> None:
    """The top View's bar has one overflow, `identifier`, whose last item opens `module`."""
    menu = bar_menus(shown.views()[-1])
    assert list(menu) == [identifier]
    item = list(menu[identifier].items or [])[-1]
    assert identifier_of(item) == ITEM
    await shown.click(item)
    assert shown.launcher.launched == [link_to(module)]


# ------------------------------------------------------------------ the item


def test_the_link_is_the_module_at_this_build_s_tag() -> None:
    """The link names the version's tag, not `main`, and the module's file (D-461)."""
    assert source_link(URL, "pycon_us.screens.now") == (
        f"{URL}/blob/v{pycon_us.__version__}/src/pycon_us/screens/now.py"
    )
    assert source_link(f"{URL}/", "pycon_us.screens.now") == source_link(
        URL, "pycon_us.screens.now"
    )


@pytest.mark.parametrize("module", sorted(set(EVERY_PAGE.values())))
def test_the_link_of_every_screen_names_a_file_of_the_repository(module: str) -> None:
    """A screen's module is a file under `src/`, where the link looks for it."""
    src = Path(pycon_us.__file__).parents[1]
    assert (src / f"{module.replace('.', '/')}.py").is_file()


def test_nothing_exists_while_the_repository_is_private(
    svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `SOURCE_URL` None there is no item and no menu, whatever the module."""
    monkeypatch.setattr(menus, "SOURCE_URL", None)
    assert view_source_items(svc, "pycon_us.screens.now") == []
    assert source_menu(svc, "pycon_us.screens.now") == []


async def test_the_item_is_a_named_link_that_opens_the_in_app_browser(
    svc: Services, page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The item has its id, is read "View source, Opens in browser", and opens the link.

    It is never disabled: offline, the in-app browser's own page says so, as for any
    other web link (D-461).
    """
    source_url_set(monkeypatch)
    (item,) = view_source_items(svc, "pycon_us.screens.now")
    assert identifier_of(item) == ITEM
    assert not item.disabled
    text = menu_text(item)
    assert text.value == VIEW_SOURCE
    assert text.semantics_label == f"{VIEW_SOURCE}\nOpens in browser"
    tile = cast(ft.ListTile, cast(ft.Semantics, item.content).content)
    assert cast(ft.Semantics, tile.title).link is True
    await cast(Any, item.on_click)()
    launcher = cast(MemoryLauncher, svc.launcher)
    assert launcher.launched == [link_to("pycon_us.screens.now")]


# ------------------------------------------------------------------ AppScaffold


def test_the_scaffold_leaves_the_bar_alone_while_private(
    hooks: Hooks, page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `SOURCE_URL` None a bar holds its own actions: no icon, no empty menu."""
    monkeypatch.setattr(menus, "SOURCE_URL", None)
    action = ft.IconButton(ft.Icons.SEARCH)
    bare = view_at(hooks, page, "/more/wifi", source="pycon_us.screens.wifi")
    assert app_bar(bare).actions == []
    view = view_at(
        hooks, page, "/more/wifi", source="pycon_us.screens.wifi", actions=[action]
    )
    assert app_bar(view).actions == [action]


def test_the_scaffold_ends_the_bar_in_view_source_once_public(
    hooks: Hooks, page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once set, a screen's own actions come first, then the overflow, "More options"."""
    source_url_set(monkeypatch)
    action = ft.IconButton(ft.Icons.SEARCH)
    view = view_at(
        hooks, page, "/more/wifi", source="pycon_us.screens.wifi", actions=[action]
    )
    actions = app_bar(view).actions or []
    assert actions[0] is action
    menu = bar_menus(view)["app.overflow"]
    assert menu.tooltip == menus.MORE_OPTIONS
    assert [identifier_of(i) for i in menu.items or []] == [ITEM]


def test_a_screen_with_its_own_menu_gets_no_second_one(
    hooks: Hooks, page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`source=None`: the screen's own menu lists the item, so the bar adds none."""
    source_url_set(monkeypatch)
    assert app_bar(view_at(hooks, page, "/more/wifi", source=None)).actions == []


# ------------------------------------------------------------------ every route


def test_every_route_and_drill_kind_is_covered() -> None:
    """The pages hold every route's screen and all seven of the drill's."""
    assert len(EVERY_PAGE) > 40
    assert {"/now", "/search", "/now/staff/lead", "/more/app/licences/python"} <= set(
        EVERY_PAGE
    )
    assert set(DRILL_PAGES) <= set(EVERY_PAGE)


@pytest.mark.parametrize("location", sorted(EVERY_PAGE))
async def test_no_screen_changes_while_the_repository_is_private(
    open_at: Open, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    """With `SOURCE_URL` None, a bar has only its own overflow, without the item."""
    monkeypatch.setattr(menus, "SOURCE_URL", None)
    shown = await open_at(location)
    own = OWN_MENUS.get(location)
    assert list(bar_menus(shown.views()[-1])) == ([own] if own else [])
    assert not shown.has("app.overflow")
    assert not shown.has(ITEM)


@pytest.mark.parametrize(("location", "module"), sorted(EVERY_PAGE.items()))
async def test_every_screen_opens_its_own_module(
    open_at: Open, monkeypatch: pytest.MonkeyPatch, location: str, module: str
) -> None:
    """Once set, each bar has one overflow, ending in View source of its screen's module."""
    source_url_set(monkeypatch)
    shown = await open_at(location)
    own = OWN_MENUS.get(location, "app.overflow")
    await assert_one_overflow_ending_in_view_source(shown, own, module)


# ------------------------------------------------------------------ conditional menus


async def test_my_schedule_lists_it_in_its_menu_with_something_to_export(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a saved session, My schedule's own menu ends in it; no second overflow."""
    source_url_set(monkeypatch)
    shown = await open_at("/my-schedule", saved=("31",))
    await assert_one_overflow_ending_in_view_source(
        shown, "my_schedule.overflow", "pycon_us.screens.my_schedule"
    )


async def test_a_session_without_its_own_menu_gets_the_scaffold_s(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A break, with no public page and no star, has only the scaffold's overflow."""
    source_url_set(monkeypatch)
    notice = next(
        s for s in DATA.sessions.values() if not s.url and is_notice(s, YEAR.conference)
    )
    shown = await open_at(f"/schedule/session/{notice.id}")
    await assert_one_overflow_ending_in_view_source(
        shown, "app.overflow", session.__name__
    )


async def test_a_track_without_add_all_gets_the_scaffold_s(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The notices' page offers no Add all: only the scaffold's overflow."""
    source_url_set(monkeypatch)
    shown = await open_at("/more/tracks/notices")
    await assert_one_overflow_ending_in_view_source(
        shown, "app.overflow", "pycon_us.screens.track"
    )


async def test_another_year_s_changes_get_the_scaffold_s(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another year's change log has no Mark all as seen: only the scaffold's overflow."""
    source_url_set(monkeypatch)
    shown = await open_at("/schedule/changes/2025")
    await assert_one_overflow_ending_in_view_source(
        shown, "app.overflow", schedule_changes.__name__
    )


async def test_a_map_without_a_tour_gets_the_scaffold_s(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A year without the venue tour has no Map menu: only the scaffold's overflow."""
    source_url_set(monkeypatch)
    monkeypatch.setattr(
        links, "YEAR", replace(YEAR, map=replace(YEAR.map, tour_url=""))
    )
    shown = await open_at("/map")
    await assert_one_overflow_ending_in_view_source(
        shown, "app.overflow", "pycon_us.screens.map"
    )


async def test_an_unknown_plan_gets_the_scaffold_s(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan that isn't there has no viewer's menu: only the scaffold's overflow.

    The one state of the `ALWAYS_OWN_MENU` screens that must keep `__name__`, which
    the source scan below allows to be None for the whole module.
    """
    source_url_set(monkeypatch)
    shown = await open_at("/map/plan/not-a-plan")
    assert shown.has("plan.not_found")
    await assert_one_overflow_ending_in_view_source(
        shown, "app.overflow", plan.__name__
    )


def test_a_sprints_year_without_links_has_a_menu_only_once_public(
    svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the year's two URLs, Sprints' menu holds View source, or doesn't exist."""
    info: Any = SimpleNamespace(sprints_url="", sprint_submit_url="")
    monkeypatch.setattr(menus, "SOURCE_URL", None)
    assert sprints_screen._menu(info, svc) == []
    source_url_set(monkeypatch)
    view = ft.View(appbar=ft.AppBar(actions=sprints_screen._menu(info, svc)))
    (button,) = bar_menus(view).values()
    assert [identifier_of(i) for i in button.items or []] == [ITEM]


# ------------------------------------------------------------------ every state


SCAFFOLDS = {"AppScaffold", "ScanScreen", "picker_page", "Reading", "NotAvailable"}
"""What takes a screen's `source`: the scaffold and the staff tools' shared pages."""

ALWAYS_OWN_MENU = {"plan", "schedule", "sprints"}
"""The screens whose main state has its menu whatever happens, and may pass None."""

UI = Path(pycon_us.__file__).parent / "ui"
SCREENS = Path(pycon_us.__file__).parent / "screens"


def source_arguments(path: Path) -> Iterator[str]:
    """Yield the `source` each scaffold call in the module at `path` is given."""
    for node in ast.walk(ast.parse(path.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in SCAFFOLDS
        ):
            (argument,) = (k for k in node.keywords if k.arg == "source")
            yield ast.unparse(argument.value)


@pytest.mark.parametrize("path", sorted(SCREENS.glob("*.py")), ids=lambda p: p.stem)
def test_every_state_of_a_screen_names_its_own_module(path: Path) -> None:
    """A not-found or signed-out state passes `__name__` too: only a menu passes None.

    The real Router reaches one state per screen; this reaches the others, such as a
    staff tool's scan screen, which needs a signed-in account.
    """
    for argument in source_arguments(path):
        if argument == "None":
            assert path.stem in ALWAYS_OWN_MENU
        else:
            assert "__name__" in argument


@pytest.mark.parametrize("name", ["scan_screen.py", "staff_picker.py"])
def test_the_staff_pages_pass_on_their_tool_s_module(name: str) -> None:
    """A shared page opens the tool's module, not `ui/scan_screen.py`, its own."""
    assert set(source_arguments(UI / name)) == {"source"}
