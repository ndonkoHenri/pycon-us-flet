"""Tests for the status strip: `StatusStrip`'s line, layout and refreshes (D-200).

The strip's body runs outside a renderer, with the fixtures of `tests/strip.py` and
`tests/chrome.py`: the hooks it calls (`ft.use_effect`, `ft.use_state` and the
store hooks) are replaced by `Hooks`, and a fake page is bound as Flet binds a
session's page. Its minute tick is `test_status_strip_ticks.py`'s. What the strip
looks like at 200 % text is checked on devices (#76's, #87's and #195's PRs).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.feed_refresh import Status
from pycon_us.services import Services, api
from pycon_us.state import Conference
from pycon_us.theme import DARK_TOKENS, HC_DARK_TOKENS
from pycon_us.ui import status_strip
from pycon_us.ui.status_strip import schedule_line, strip_line
from tests import chrome, strip
from tests.fake_page import FakePage, Hooks
from tests.strip import PACIFIC, Network, render_strip, strip_parts

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference = chrome.year, chrome.svc, chrome.page, chrome.conference
hooks, network = strip.hooks, strip.network


def press(button: ft.TextButton) -> asyncio.Task[None]:
    """Run a button's async handler as Flet does, as a task of the event loop."""
    assert button.on_click is not None
    return asyncio.create_task(cast(Callable[[], Any], button.on_click)())


# ------------------------------------------------------------------ StatusStrip

FETCHED = datetime(2026, 5, 12, 10, 42, tzinfo=PACIFIC)  # a Tuesday


@pytest.mark.parametrize(
    ("status", "fetched_at", "line"),
    [
        ("fresh", FETCHED, None),
        ("refreshing", FETCHED, "Updating the schedule…"),
        ("stale", FETCHED, "Updated 9 hours ago"),
        ("stale", None, "No schedule yet"),
        ("offline", FETCHED, "Offline · schedule from Tue, May 12, 10:42 AM"),
        ("problem", FETCHED, "Couldn't update · schedule from Tue, May 12, 10:42 AM"),
        ("offline", None, "Offline · no schedule yet"),
        ("problem", None, "Couldn't update · no schedule yet"),
    ],
)
def test_the_strip_says_why_the_data_is_not_fresh(
    status: Status, fetched_at: datetime | None, line: str | None
) -> None:
    """Each status gives its line, with or without a fetch time; fresh gives none."""
    now = FETCHED + timedelta(hours=9, minutes=5)
    assert strip_line(status, fetched_at, now, PACIFIC, use_24h=False) == line


def test_the_strip_writes_times_in_conference_time_and_the_device_format() -> None:
    """A UTC fetch time is written in conference time, in the 24-hour format."""
    fetched_utc = FETCHED.astimezone(ZoneInfo("UTC"))
    line = strip_line("offline", fetched_utc, FETCHED, PACIFIC, use_24h=True)
    assert line == "Offline · schedule from Tue, May 12, 10:42"


def test_the_schedule_line_names_the_source_and_its_age() -> None:
    """The schedule line names the source and its age, or says there is none yet."""
    now = FETCHED + timedelta(hours=3)
    assert schedule_line("cache", FETCHED, now) == "From the cache, updated 3 hours ago"
    assert schedule_line("network", FETCHED, now) == (
        "From the feed, updated 3 hours ago"
    )
    assert (
        schedule_line("bundled", now, now) == "Bundled with the app, updated just now"
    )
    assert schedule_line("none", None, now) == "No schedule yet"


def test_the_schedule_line_counts_the_age_to_the_clock_the_app_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a `now` the age runs to `clock.now()`, which a fake clock moves."""
    monkeypatch.setattr(clock, "now", lambda: FETCHED + timedelta(days=2))
    assert schedule_line("network", FETCHED) == "From the feed, updated 2 days ago"


def strip_rows(strip: ft.Semantics) -> tuple[ft.Row, ft.Row]:
    """The strip's row (the line and Refresh) and the line's row (the icon and words)."""
    box = cast(ft.Container, strip.content)
    padded = cast(ft.Container, cast(ft.Column, box.content).controls[0])
    row = cast(ft.Row, padded.content)
    line_box = cast(ft.Container, row.controls[0])
    return row, cast(ft.Row, line_box.content)


def icon_of(strip: ft.Semantics) -> ft.Icon:
    """The strip's icon, beside its line."""
    _, line_row = strip_rows(strip)
    icon = line_row.controls[0]
    assert isinstance(icon, ft.Icon)
    return icon


@dataclass(eq=False)
class StripRenders:
    """Renders the strip at every change of the store, as a subscribed strip does.

    The test keeps it: an observable holds its listeners weakly.
    """

    conference: Conference
    strips: list[ft.Semantics] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Subscribe to the conference store."""
        assert isinstance(self.conference, ft.Observable)
        self.conference.subscribe(self)

    def __call__(self, _sender: object, _name: str | None) -> None:
        """Render the strip again for the store's change."""
        self.strips.append(render_strip())


@pytest.fixture
def fake_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Two days before the conference, so a 25 h old feed is stale (D-32)."""
    now = datetime(2026, 5, 11, 12, 0, tzinfo=PACIFIC)
    monkeypatch.setattr(clock, "now", lambda: now)
    return now


def test_the_strip_is_hidden_while_the_data_is_fresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    """With data fetched an hour ago, the strip is hidden."""
    conference.fetched_at = fake_now - timedelta(hours=1)
    strip = render_strip()
    assert strip.visible is False


def test_a_stale_strip_is_a_live_region_with_refresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    """A day-old feed shows the strip as a live region, with Refresh enabled, no bar."""
    conference.fetched_at = fake_now - timedelta(hours=25)
    strip = render_strip()
    text, button, progress = strip_parts(strip)
    assert strip.visible is True
    assert strip.live_region is True
    assert strip.identifier == "app.status"
    assert text.value == "Updated 1 day ago"
    assert button.disabled is False
    assert button.on_click is not None
    assert progress.visible is False


async def test_while_a_refresh_the_user_asked_for_runs_it_says_so_and_disables_refresh(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    fake_now: datetime,
    network: Network,
) -> None:
    """During the user's refresh, the strip says it is updating, and disables Refresh.

    Its icon turns neutral and the indeterminate bar shows.
    """
    conference.fetched_at = fake_now - timedelta(hours=25)
    tap = press(strip_parts(render_strip())[1])  # Refresh
    await network.arrived.wait()

    strip = render_strip()
    text, button, progress = strip_parts(strip)
    assert strip.visible is True
    assert text.value == "Updating the schedule…"
    assert icon_of(strip).color == ft.Colors.ON_SURFACE_VARIANT
    assert button.disabled is True
    assert progress.visible is True
    assert progress.value is None  # indeterminate
    network.released.set()
    await tap


async def test_an_automatic_refresh_over_fresh_data_keeps_the_strip_hidden(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    """An automatic refresh over hour-old data runs with the strip still hidden."""
    conference.fetched_at = fake_now - timedelta(hours=1)
    conference.start_refresh_if_due(svc.storage, svc.year)
    await network.arrived.wait()

    assert conference.refreshing
    assert render_strip().visible is False  # nothing appears, nothing moves (D-181)


def test_a_wrapped_line_keeps_its_icon_beside_its_first_line(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    """The strip's 16 dp icon scales with the text and sits by the line's first line.

    At 200 % text the line wraps; the icon tops it and is one line tall at any text
    size, so it sits beside the first line, not above it or by the block's middle
    (#195). A 16 dp icon that did not scale topped a line three times its height.
    """
    conference.fetched_at = fake_now - timedelta(hours=25)
    strip = render_strip()
    _, line_row = strip_rows(strip)
    icon, text = line_row.controls
    assert isinstance(icon, ft.Icon) and isinstance(text, ft.Text)
    assert line_row.vertical_alignment == ft.CrossAxisAlignment.START
    assert text.theme_style == ft.TextThemeStyle.BODY_SMALL  # a 16 dp line (12/16)
    assert icon.size == status_strip.ICON_SIZE == 16
    assert icon.apply_text_scaling is True


def test_a_line_too_long_for_the_buttons_side_moves_the_button_under_it(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    """The strip's row wraps, so Refresh moves under a line too long to share its run.

    One run while the line fits beside Refresh (the line centred against the 48 dp
    button, the button at the end); at large text the button takes a run of its own, so
    the line keeps the strip's width instead of a column a word wide (#195).
    """
    conference.fetched_at = fake_now - timedelta(hours=25)
    strip = render_strip()
    row, line_row = strip_rows(strip)
    text = line_row.controls[1]
    assert row.wrap is True
    # A wrap is as wide as its runs: the strip's column stretches it to the width.
    column = cast(ft.Column, cast(ft.Container, strip.content).content)
    assert column.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert row.alignment == ft.MainAxisAlignment.SPACE_BETWEEN
    assert row.vertical_alignment == ft.CrossAxisAlignment.CENTER
    # The line measures its own width, so the wrap can tell when the button fits.
    assert line_row.tight is True
    assert line_row.expand is None
    assert text.expand and text.expand_loose is True
    # Alone on its run, Refresh's label starts under the words, and the line keeps
    # off the strip's top edge; beside the button, both are centred as before.
    line_box, button_box = cast(list[ft.Container], row.controls)
    # 8 + a 16 dp line + 8 still fits the 48 dp button's height at 100 %.
    assert line_box.padding == ft.Padding.symmetric(vertical=8)
    assert button_box.padding == ft.Padding.only(left=16)  # 16 + 12 - the label's 12
    assert line_row.spacing == 12 and icon_of(strip).size == 16
    assert row.spacing == 0  # the indent is the gap beside the line


def looks(strip: ft.Semantics) -> tuple[object, ...]:
    """What a sighted user and a screen reader get from the strip, but its bar."""
    text, button, _ = strip_parts(strip)
    icon = icon_of(strip)
    return strip.visible, icon.icon, icon.color, text.value, button.disabled


async def test_an_automatic_refresh_over_an_offline_strip_shows_only_the_bar(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    """An automatic refresh that fails offline again only shows, then hides, the bar."""
    conference.fetched_at = datetime(2026, 5, 11, 10, 42, tzinfo=PACIFIC)
    conference.problem = "offline"  # the last refresh got no answer
    network.error = api.NetworkError("ConnectError: still offline")
    offline = looks(render_strip())
    assert offline == (
        True,
        ft.Icons.CLOUD_OFF_OUTLINED,
        DARK_TOKENS.warning,
        "Offline · schedule from Mon, May 11, 10:42 AM",
        False,
    )
    renders = StripRenders(conference)

    task = conference.start_refresh_if_due(svc.storage, svc.year)  # the 15-min tick
    assert task is not None
    await network.arrived.wait()
    during = render_strip()
    network.released.set()
    await task
    after = render_strip()

    # Line, icon and button never changed, so the live region announces nothing new;
    # only the bar came and went, in its fixed slot (D-181).
    assert {looks(strip) for strip in [during, after, *renders.strips]} == {offline}
    assert strip_parts(during)[2].visible is True
    assert strip_parts(after)[2].visible is False
    assert [strip_parts(strip)[2].visible for strip in renders.strips] == [True, False]


async def test_refresh_during_a_quiet_refresh_joins_it_and_says_so_at_once(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    """Refresh joins a quiet refresh, says so at once, and sends no second request."""
    conference.fetched_at = fake_now - timedelta(hours=25)
    quiet = conference.start_refresh_if_due(svc.storage, svc.year)
    assert quiet is not None
    await network.arrived.wait()
    strip = render_strip()
    assert strip_parts(strip)[0].value == "Updated 1 day ago"
    renders = StripRenders(conference)

    tap = press(strip_parts(strip)[1])  # Refresh, while the quiet refresh runs
    await asyncio.sleep(0)  # the handler runs up to its wait

    (joined,) = renders.strips  # the tap re-renders the strip at once
    text, button, progress = strip_parts(joined)
    assert text.value == "Updating the schedule…"
    assert button.disabled is True
    assert progress.visible is True
    assert conference._task is quiet
    network.released.set()
    await tap
    assert quiet.done()
    assert network.requests == 1  # one request for both (D-145)


@pytest.mark.parametrize("high_contrast", [False, True], ids=["standard", "hc"])
def test_in_high_contrast_lines_draw_the_strip_s_band(
    hooks: Hooks,
    page: FakePage,
    monkeypatch: pytest.MonkeyPatch,
    high_contrast: bool,
) -> None:
    """In HC, where its fill is the surface, 1 dp lines above and below draw the strip.

    Outside HC its tonal fill is its edge, and it has no border (D-306).
    """
    tokens = HC_DARK_TOKENS if high_contrast else DARK_TOKENS
    monkeypatch.setattr(status_strip, "use_tokens", lambda: tokens)
    box = render_strip().content
    assert isinstance(box, ft.Container)
    line = ft.BorderSide(1, ft.Colors.OUTLINE)
    expected = ft.Border.only(top=line, bottom=line) if high_contrast else None
    assert box.border == expected
