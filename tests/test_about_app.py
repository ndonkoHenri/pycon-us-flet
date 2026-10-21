"""Tests for About this app: its data, its build, the 7-tap unlock and its links.

#88 (D-73, D-187), #441 (D-292) and #443 (D-297). ``AboutApp``, ``ConferenceData`` and
``HelpUsFixIt`` run outside a renderer: their hooks and ``AppScaffold`` are replaced, an external link row's body runs
inline, and a fake page is bound as Flet binds a session's page. How the page looks and
reads is checked on devices (the PRs).
"""

import inspect
import json
import platform
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.components.hooks.use_ref import MutableRef

import pycon_us
from pycon_us import clock
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import about_app
from pycon_us.screens.about_app import (
    UNLOCK_TAPS,
    AboutApp,
    ConferenceData,
    HelpUsFixIt,
    shown_url,
)
from pycon_us.services import Services, api, errors
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import rows as rows_module
from pycon_us.ui import share as share_module
from pycon_us.ui.share import DIAGNOSTICS_SHARED, LOG_SHARED, WITH_LOG, WITHOUT_LOG
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPaths,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
    bound,
    phone_margin,
)
from tests.feeds import recorded

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
    page, as Flet's do.
    """
    ref = MutableRef(0)
    unsaved: list[bool] = [False]  # the one use_state: whether the unlock was saved

    def use_state(initial: bool) -> tuple[bool, Callable[[bool], None]]:
        return unsaved[0], lambda value: unsaved.__setitem__(0, value)

    monkeypatch.setattr(ft, "use_ref", lambda initial=None: ref)
    monkeypatch.setattr(ft, "use_state", use_state)
    monkeypatch.setattr(about_app, "use_services", lambda: svc)
    monkeypatch.setattr(about_app, "use_prefs", lambda: prefs)
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


def test_the_page_says_which_build_this_is(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The page lists the app's version, Python's and Flet's, then its licences."""
    scaffold = render()
    assert scaffold["title"] == "About this app"
    rows = tiles(scaffold)
    assert [(title, tile.subtitle) for title, tile in rows.items()] == [
        ("Version", pycon_us.__version__),
        ("Python", platform.python_version()),
        ("Flet", "source build"),  # while the source pin lasts (development.md §2.2)
        ("Licences", None),
    ]


def test_the_page_s_sections_are_its_data_its_build_its_links_and_help(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The opening, Conference data, This build, Links, then Help us fix it.

    The page's own headings are level 2; Help us fix it's is its section's (below).
    """
    controls = body_of(render())
    assert controls[1] is CONFERENCE_DATA  # right under the opening (D-292)
    assert headings(controls) == [("This build", 2), ("Links", 2)]
    assert controls[-1] is HELP_US_FIX_IT  # after Links (D-297)


def test_the_page_names_the_app_and_says_it_is_not_the_psf_s(
    render: Callable[[], dict[str, Any]],
) -> None:
    """A level-2 heading names the app, over lines saying it is not the PSF's."""
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    header = body.controls[0]
    assert isinstance(header, ft.Container) and isinstance(header.content, ft.Column)
    name, lines = header.content.controls
    assert isinstance(name, ft.Semantics) and name.header
    assert name.heading_level == 2  # under the bar's "About this app" (D-211)
    # Nodes of their own, so the name is read alone, and before the lines under it.
    assert isinstance(lines, ft.Semantics) and name.container and lines.container
    assert isinstance(lines.content, ft.Column)
    about, not_official = lines.content.controls
    assert isinstance(name.content, ft.Text)
    assert name.content.value == pycon_us.APP_NAME
    assert isinstance(about, ft.Text) and isinstance(not_official, ft.Text)
    assert about.value == "A companion for PyCon US 2026, built with Python and Flet."
    assert not_official.value == "Not an official PSF app."  # D-36


def test_the_version_row_carries_its_identifier_for_ui_flows(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The Version row's merged node carries the ``about_app.version`` id."""
    rows = [c for c in body_of(render()) if isinstance(c, ft.MergeSemantics)]
    identifiers = [cast(ft.Semantics, row.content).identifier for row in rows]
    assert identifiers == ["about_app.version", "about_app.licences", "about_app.flet"]


def test_licences_opens_its_page_under_about_this_app(
    render: Callable[[], dict[str, Any]], page: FakePage
) -> None:
    """The Licences row opens ``/more/app/licences``, so Back returns here (D-296)."""
    tile = tiles(render())["Licences"]
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == ["/more/app/licences"]


async def test_licences_comes_after_the_developer_row(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Unlocked, Developer options stays right under the build's rows, where the taps were."""
    await tap_version(render, 7)
    controls = body_of(render())
    kinds = [
        "developer" if isinstance(c, ft.Semantics) and c.live_region else c
        for c in controls
    ]
    developer = kinds.index("developer")
    licences = controls[developer + 1]
    assert isinstance(licences, ft.MergeSemantics)
    assert cast(ft.Semantics, licences.content).identifier == "about_app.licences"


def developer_row(scaffold: dict[str, Any]) -> ft.ListTile | None:
    """The row the unlock adds, or None."""
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    for row in body.controls:
        if isinstance(row, ft.Semantics) and row.live_region:
            link = row.content
            assert isinstance(link, ft.MergeSemantics)
            assert isinstance(link.content, ft.Semantics)
            assert link.content.identifier == "about_app.developer"
            tile = link.content.content
            assert isinstance(tile, ft.ListTile)
            return tile
    return None


async def test_six_taps_unlock_nothing(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage
) -> None:
    """Six taps on Version leave Developer locked and unlisted, with no dialog."""
    await tap_version(render, UNLOCK_TAPS - 1)
    assert not prefs.developer
    assert developer_row(render()) is None
    assert page.dialogs == []


async def test_the_seventh_tap_unlocks_developer_and_keeps_it_unlocked(
    render: Callable[[], dict[str, Any]], prefs: Prefs, page: FakePage, svc: Services
) -> None:
    """The seventh tap stores the unlock and adds a Developer row that opens it."""
    assert UNLOCK_TAPS == 7
    await tap_version(render, 7)
    assert prefs.developer
    stored = cast(MemoryPrefs, svc.storage.prefs).values["pycon.dev"]
    assert json.loads(stored) == {"unlocked": True}  # survives a relaunch (D-187)
    assert errors._details is True  # handler errors now say what failed
    # Said in place, where the taps were, not in a SnackBar (D-29, D-210).
    assert page.dialogs == []
    row = developer_row(render())
    assert row is not None
    assert (row.title, row.subtitle) == ("Developer options", "On")
    cast(Callable[[], None], row.on_click)()
    assert page.navigated == ["/more/developer"]


async def test_the_unlock_keeps_the_other_developer_options(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """The unlock adds ``unlocked`` to the stored options and keeps the rest."""
    prefs.dev = {"feed_url": "http://127.0.0.1:8000/conference-2026.json"}
    await tap_version(render, 7)
    assert prefs.dev == {
        "feed_url": "http://127.0.0.1:8000/conference-2026.json",
        "unlocked": True,
    }


async def test_taps_once_it_is_on_change_nothing(
    render: Callable[[], dict[str, Any]], svc: Services
) -> None:
    """Taps after the unlock write nothing more to the prefs."""
    await tap_version(render, 7)
    writes = dict(cast(MemoryPrefs, svc.storage.prefs).values)
    await tap_version(render, 14)
    assert cast(MemoryPrefs, svc.storage.prefs).values == writes


async def test_when_not_embedded_developer_is_listed_without_taps(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In the companion app Developer is listed at once, and taps store nothing."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", True)  # the companion app
    assert developer_row(render()) is not None
    await tap_version(render, 7)
    assert prefs.dev == {}  # nothing to unlock or store
    assert errors._details is False  # the companion app shows details by itself


async def test_an_unlock_that_cannot_be_saved_holds_for_the_session_and_says_so(
    render: Callable[[], dict[str, Any]], prefs: Prefs, svc: Services
) -> None:
    """An unlock that can't be stored holds in memory, and its row says so."""
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await tap_version(render, 7)
    assert prefs.developer  # D-120: kept in memory
    row = developer_row(render())
    assert row is not None
    assert row.subtitle == "On until you close the app"


# ------------------------------------------------------------------ Links


async def test_flet_opens_in_the_in_app_browser_and_reads_as_a_link(
    render: Callable[[], dict[str, Any]], svc: Services
) -> None:
    """The Flet row is a link to flet.dev that opens, and says so, in the browser."""
    node = link_rows(render())["about_app.flet"]
    assert node.link  # a link, not a button (INFO-14)
    tile = node.content
    assert isinstance(tile, ft.ListTile)
    assert (tile.title, tile.subtitle) == ("Flet website", "flet.dev")
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.semantics_label == "Opens in browser"  # D-182
    await cast(Callable[[], Any], tile.on_click)()
    launcher = cast(MemoryLauncher, svc.launcher)
    assert launcher.launched == [
        ("https://flet.dev", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


def test_the_source_url_is_unset_until_the_repository_is_public() -> None:
    """``SOURCE_URL`` ships as None until P4 makes the repository public (D-88, D-292)."""
    assert pycon_us.SOURCE_URL is None


def test_no_source_code_row_while_the_repository_is_private(
    render: Callable[[], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``SOURCE_URL`` None, Links lists Flet alone: no row links to a private repository."""
    monkeypatch.setattr(about_app, "SOURCE_URL", None)
    assert list(link_rows(render())) == ["about_app.flet"]


async def test_a_source_url_adds_a_source_code_row_after_flet(
    render: Callable[[], dict[str, Any]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once ``SOURCE_URL`` is set, a Source code row opens it in the in-app browser."""
    url = "https://example.org/conf-companion"
    monkeypatch.setattr(about_app, "SOURCE_URL", url)
    found = link_rows(render())
    assert list(found) == ["about_app.flet", "about_app.source"]
    tile = found["about_app.source"].content
    assert isinstance(tile, ft.ListTile)
    assert (tile.title, tile.subtitle) == ("Source code", "example.org/conf-companion")
    await cast(Callable[[], Any], tile.on_click)()
    launcher = cast(MemoryLauncher, svc.launcher)
    assert launcher.launched == [(url, ft.LaunchMode.IN_APP_BROWSER_VIEW)]


def test_a_url_is_shown_without_its_scheme_or_a_trailing_slash() -> None:
    """A row's address drops ``https://`` and a final slash, and keeps the path."""
    assert shown_url("https://flet.dev") == "flet.dev"
    assert shown_url("https://flet.dev/") == "flet.dev"
    assert shown_url("https://example.org/a/b/") == "example.org/a/b"


# ------------------------------------------------------------------ Conference data


@pytest.fixture
async def conference(svc: Services) -> Conference:
    """A Conference store that has published the bundled 2026 snapshot, as offline."""
    store = Conference()
    await store.load_local(svc.storage, svc.year)
    return store


@pytest.fixture
def section(
    monkeypatch: pytest.MonkeyPatch, svc: Services, conference: Conference
) -> Callable[[], list[ft.Control]]:
    """Render ``ConferenceData`` over ``svc`` and ``conference``: its controls."""
    monkeypatch.setattr(about_app, "use_services", lambda: svc)
    monkeypatch.setattr(about_app, "use_conference", lambda: conference)
    monkeypatch.setattr(about_app, "use_minute", lambda: 0)

    def render() -> list[ft.Control]:
        column = inspect.unwrap(ConferenceData)()
        assert isinstance(column, ft.Column)
        return column.controls

    return render


def data_rows(controls: list[ft.Control]) -> dict[str, str]:
    """The section's rows: each title and its second line."""
    found = {}
    for row in controls:
        if isinstance(row, ft.MergeSemantics):
            assert isinstance(row.content, ft.Semantics)
            assert row.content.identifier == "about_app.schedule"
            row = row.content.content
        if isinstance(row, ft.ListTile):
            found[str(row.title)] = str(row.subtitle)
    return found


def test_the_section_is_a_level_2_heading_over_the_conference_and_schedule(
    section: Callable[[], list[ft.Control]],
) -> None:
    """Conference data heads the year's conference and the schedule's line, in order."""
    controls = section()
    assert headings(controls) == [("Conference data", 2)]
    assert list(data_rows(controls)) == ["Conference", "Schedule"]
    assert data_rows(controls)["Conference"] == "PyCon US 2026"  # year data (D-35)


def test_a_first_start_offline_says_the_schedule_is_bundled(
    section: Callable[[], list[ft.Control]], svc: Services, conference: Conference
) -> None:
    """Offline on a first start, the line says the schedule is the one bundled."""
    captured = svc.year.conference.snapshot_captured_at
    assert captured is not None
    assert conference.source == "bundled"
    clock.start_fake_clock(captured + timedelta(days=3, minutes=1))
    assert data_rows(section())["Schedule"] == (
        "Bundled with the app, updated 3 days ago"
    )


async def test_after_a_refresh_the_line_says_from_the_feed_and_its_age_moves(
    section: Callable[[], list[ft.Control]],
    svc: Services,
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a refresh it says "From the feed"; the fake clock then moves its age."""

    async def serve(url: str, **_: Any) -> bytes:
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", serve)
    await conference.refresh(svc.storage, svc.year)
    assert data_rows(section())["Schedule"] == "From the feed, updated just now"
    fetched = conference.fetched_at
    assert fetched is not None
    clock.start_fake_clock(fetched + timedelta(minutes=5, seconds=30))
    assert data_rows(section())["Schedule"] == "From the feed, updated 5 minutes ago"
    clock.start_fake_clock(fetched + timedelta(hours=2, seconds=30))
    assert data_rows(section())["Schedule"] == "From the feed, updated 2 hours ago"


def test_the_section_ticks_with_the_minute_and_reads_the_store(
    section: Callable[[], list[ft.Control]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A render calls ``use_minute()`` and ``use_conference()``: the line keeps up."""
    calls: list[str] = []
    monkeypatch.setattr(about_app, "use_minute", lambda: calls.append("minute") or 0)
    use_conference = about_app.use_conference
    monkeypatch.setattr(
        about_app,
        "use_conference",
        lambda: calls.append("conference") or use_conference(),
    )
    section()
    assert sorted(calls) == ["conference", "minute"]


# ------------------------------------------------------------------ Help us fix it


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


@pytest.fixture
def help_section(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    conference: Conference,
    prefs: Prefs,
    page: FakePage,
    tmp_path: Path,
) -> Callable[[], list[ft.Control]]:
    """Render ``HelpUsFixIt`` in a packaged build with a one-line log: its controls."""
    log = tmp_path / "console.log"
    log.write_text("12:00:00.000 INFO pycon_us.app: started\n")
    cast(MemoryPaths, svc.paths).console_log = str(log)
    states = States()
    monkeypatch.setattr(ft, "use_state", states.use_state)
    answer_report_hooks(monkeypatch, svc, conference, prefs)
    monkeypatch.setattr(about_app, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(about_app, "SOURCE_URL", None)
    monkeypatch.setattr(
        rows_module, "_ExternalLinkTile", inspect.unwrap(rows_module._ExternalLinkTile)
    )
    monkeypatch.setattr(rows_module, "use_services", lambda: svc)

    def render() -> list[ft.Control]:
        states.index = 0
        column = inspect.unwrap(HelpUsFixIt)()
        assert isinstance(column, ft.Column)
        return column.controls

    return render


def identified(controls: list[ft.Control]) -> dict[str, ft.Semantics]:
    """The identified nodes among ``controls``, merged rows' included, by identifier."""
    found = {}
    for control in controls:
        node = control.content if isinstance(control, ft.MergeSemantics) else control
        if isinstance(node, ft.Semantics) and node.identifier:
            found[node.identifier] = node
    return found


def help_tile(controls: list[ft.Control], identifier: str) -> ft.ListTile:
    """The row under ``identifier``."""
    tile = identified(controls)[identifier].content
    assert isinstance(tile, ft.ListTile)
    return tile


def text_of(value: Any) -> str:
    """The words of a tile's title or subtitle, a ``Text`` or a string."""
    return str(value.value if isinstance(value, ft.Text) else value)


def report_outcome(controls: list[ft.Control]) -> str | None:
    """The words of the line under the rows, or None while it is hidden."""
    line = identified(controls)["about_app.report_outcome"]
    assert line.live_region is True  # a screen reader says it when it changes
    if not line.visible:
        return None
    text = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    return text_of(text)


async def tap_row(render: Callable[[], list[ft.Control]], identifier: str) -> None:
    """Tap the row under ``identifier`` as Flutter would."""
    await cast(Any, help_tile(render(), identifier).on_click)()


def test_while_private_one_row_reports_a_problem_with_the_log(
    help_section: Callable[[], list[ft.Control]],
) -> None:
    """While the repository is private, Help us fix it is one Report a problem row.

    A level-2 heading over it; the row says beforehand that it sends the log and the
    diagnostics; the outcome line under it is hidden until a share ends.
    """
    controls = help_section()
    assert headings(controls) == [("Help us fix it", 2)]
    assert list(identified(controls)) == [
        "about_app.report_problem",
        "about_app.report_outcome",
    ]
    tile = help_tile(controls, "about_app.report_problem")
    assert text_of(tile.title) == "Report a problem"
    assert text_of(tile.subtitle) == WITH_LOG
    assert report_outcome(controls) is None


async def test_report_a_problem_shares_the_log_and_says_so_in_place(
    help_section: Callable[[], list[ft.Control]], svc: Services
) -> None:
    """A tap shares console.log with the diagnostics, then says so under the row."""
    await tap_row(help_section, "about_app.report_problem")
    [files] = cast(MemoryShare, svc.share).shared
    assert len(files) == 1
    assert report_outcome(help_section()) == LOG_SHARED[0]
    assert help_tile(help_section(), "about_app.report_problem").disabled is False


async def test_in_the_companion_app_the_row_says_it_sends_the_diagnostics_alone(
    help_section: Callable[[], list[ft.Control]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside a packaged build the row says, before the tap, that no log goes."""
    monkeypatch.setattr(share_module, "is_embedded", lambda: False)
    tile = help_tile(help_section(), "about_app.report_problem")
    assert text_of(tile.subtitle) == WITHOUT_LOG
    await tap_row(help_section, "about_app.report_problem")
    assert cast(MemoryShare, svc.share).shared == []
    assert len(cast(MemoryShare, svc.share).texts) == 1
    assert report_outcome(help_section()) == DIAGNOSTICS_SHARED[0]


async def test_the_row_is_disabled_while_the_sheet_is_up(
    help_section: Callable[[], list[ft.Control]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While the sheet is up the row is disabled, so a second tap opens no second one."""
    seen: list[bool | None] = []
    share = cast(MemoryShare, svc.share)
    share_files = share.share_files

    async def record_then_share(files: list[ft.ShareFile], **options: Any) -> Any:
        seen.append(help_tile(help_section(), "about_app.report_problem").disabled)
        return await share_files(files, **options)

    monkeypatch.setattr(share, "share_files", record_then_share)
    await tap_row(help_section, "about_app.report_problem")
    assert seen == [True]
    assert help_tile(help_section(), "about_app.report_problem").disabled is False


async def test_once_public_report_opens_a_new_issue_and_share_log_shares(
    help_section: Callable[[], list[ft.Control]],
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``SOURCE_URL`` set, Report a problem links to a new issue, Share log shares.

    The link opens in the in-app browser and reads as one (INFO-14, D-182).
    """
    monkeypatch.setattr(about_app, "SOURCE_URL", "https://example.org/conf/")
    controls = help_section()
    assert list(identified(controls)) == [
        "about_app.report_problem",
        "about_app.share_log",
        "about_app.report_outcome",
    ]
    node = identified(controls)["about_app.report_problem"]
    assert node.link
    tile = node.content
    assert isinstance(tile, ft.ListTile)
    assert text_of(tile.subtitle) == "example.org/conf/issues/new"
    await cast(Callable[[], Any], tile.on_click)()
    assert cast(MemoryLauncher, svc.launcher).launched == [
        ("https://example.org/conf/issues/new", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    await tap_row(help_section, "about_app.share_log")
    assert len(cast(MemoryShare, svc.share).shared) == 1
    assert report_outcome(help_section()) == LOG_SHARED[0]
