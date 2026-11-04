"""Tests for the Venue & hours page (`screens/venue.py`; #413, MAP-09, MAP-11, D-313).

The page runs in a real Flet session (`tests/sessions.py`) over the bundled year data,
with the clock frozen at a chosen instant (`clock.set_test_now`). How it looks, wraps
at 200 % and reads to screen readers is checked on devices (the PR).
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock, theme
from pycon_us.config import load_year
from pycon_us.screens import venue as screen
from pycon_us.state import Conference
from pycon_us.ui.buttons import ICON_PADDING
from pycon_us.year_info import Directions
from tests.fakes import MemoryClipboard
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.sessions import text_of
from tests.theme_helpers import contrast_ratio, hex_role, scheme

PACIFIC = ZoneInfo("America/Los_Angeles")
THURSDAY_10AM = datetime(2026, 5, 14, 10, 0, tzinfo=PACIFIC)
VIEW = "/more/venue"
REGISTRATION = "venue.service.registration"

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders the page at an instant, for a year and a feed."""
    try:
        async with AsyncExitStack() as stack:

            async def render(
                *,
                now: datetime = THURSDAY_10AM,
                year: int = 2026,
                feed: int | None = None,
            ) -> Shown:
                """Render the page at `now` with `year`'s data and `feed`'s feed."""
                clock.set_test_now(now)
                conference = (
                    Conference()
                    if feed is None
                    else Conference(data=processed(feed), source="bundled", version=1)
                )
                return await stack.enter_async_context(
                    showing(
                        screen.Venue,
                        screen,
                        year=load_year(year),
                        conference=conference,
                        tmp_path=tmp_path,
                        monkeypatch=monkeypatch,
                        view_path=VIEW,
                    )
                )

            yield render
    finally:
        clock.set_test_now(None)


def status_text(page: Shown, key: str = REGISTRATION) -> ft.Text:
    """The `Text` of a service's status label."""
    return cast(ft.Text, page.node(f"{key}.status").content)


def snack_texts(page: Shown) -> list[str]:
    """What the page's SnackBars said, in order."""
    return [text_of(bar.content) for bar in page.snack_bars]


@pytest.mark.parametrize(
    ("now", "label"),
    [
        (THURSDAY_10AM, "Open now · until 6:00 PM"),
        (datetime(2026, 5, 14, 7, 0, tzinfo=PACIFIC), "Opens 7:30 AM"),
        (datetime(2026, 5, 14, 18, 0, tzinfo=PACIFIC), "Opens tomorrow at 7:30 AM"),
    ],
    ids=["open", "before", "after-closing"],
)
async def test_registration_s_label_follows_the_clock(
    show: Show, now: datetime, label: str
) -> None:
    """At 10:00 PT it is open, at 07:00 it opens at 7:30, at 18:00 it opens tomorrow."""
    page = await show(now=now)
    assert status_text(page).value == label


async def test_open_now_is_live_and_read_as_words(show: Show) -> None:
    """Open now is in `live` and says "Open now, until 6:00 PM" to a screen reader."""
    page = await show()
    text = status_text(page)
    assert text.color == theme.build_tokens(dark=False, high_contrast=False).live
    assert text.semantics_label == "Open now, until 6:00 PM"


async def test_a_later_opening_is_in_the_supporting_colour(show: Show) -> None:
    """Only Open now is in `live`: a later opening is `on_surface_variant`."""
    page = await show(now=datetime(2026, 5, 14, 7, 0, tzinfo=PACIFIC))
    assert status_text(page).color == ft.Colors.ON_SURFACE_VARIANT


async def test_the_status_is_a_label_and_never_a_chip(show: Show) -> None:
    """Nothing happens on a tap, so the page has no chip and no button per service."""
    page = await show()
    assert not page.find(ft.Chip)
    assert len(page.find(ft.FilledTonalButton)) == 1  # Directions
    assert len(page.find(ft.OutlinedButton)) == 1  # Copy address


async def test_off_season_there_are_no_labels_but_the_hours_show(show: Show) -> None:
    """In March no service has a status: the cards show their hours alone."""
    page = await show(now=datetime(2026, 3, 2, 10, 0, tzinfo=PACIFIC))
    assert not page.nodes("venue.service.registration.status")
    assert page.nodes(REGISTRATION)
    # The line breaks only at its "·" (no-break spaces inside the day and the times).
    assert "Wed,\xa0May\xa013 · 7:30\xa0AM–6:00\xa0PM" in page.texts()


async def test_services_without_hours_have_no_status_and_show_their_note(
    show: Show,
) -> None:
    """Lost & found and Luggage check say their note and have no label in season."""
    page = await show()
    assert page.nodes("venue.service.lost_found")
    assert not page.nodes("venue.service.lost_found.status")
    assert not page.nodes("venue.service.luggage_check.status")
    assert "There is no luggage check this year." in page.texts()


async def test_today_s_hours_are_bold_and_say_today(show: Show) -> None:
    """Thursday's line is bold and read "…, today"; the other days are not."""
    page = await show()

    def lines(label: str) -> list[ft.Semantics]:
        """The day lines a screen reader reads as `label`."""
        return [n for n in page.find(ft.Semantics) if n.label == label]

    (today,) = lines("Thursday, May 14, 7:30 AM to 6:00 PM, today")
    assert today.exclude_semantics  # one node, the words its label's
    assert cast(ft.Text, today.content).weight == ft.FontWeight.BOLD
    friday = lines("Friday, May 15, 7:30 AM to 5:00 PM")
    assert friday and all(cast(ft.Text, n.content).weight is None for n in friday)


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        (
            ft.PagePlatform.IOS,
            (
                "https://maps.apple.com/?q=Long%20Beach%20Convention%20Center"
                "%20%28Pine%20Ave%20Entrance%29&ll=33.764444,-118.191722&dirflg=w"
            ),
        ),
        (
            ft.PagePlatform.ANDROID,
            (
                "geo:33.764444,-118.191722?q=33.764444,-118.191722"
                "(Long%20Beach%20Convention%20Center%20%28Pine%20Ave%20Entrance%29)"
            ),
        ),
    ],
    ids=["ios", "android"],
)
async def test_directions_opens_the_platform_s_maps_app(
    show: Show, platform: ft.PagePlatform, url: str
) -> None:
    """Apple Maps on iOS, the `geo:` handler on Android, both outside the app."""
    page = await show()
    page.session.page.platform = platform
    node = page.node("venue.directions")
    assert node.link  # it leaves the app (D-182)
    await page.click(cast(ft.Control, node.content))
    assert page.launcher.launched == [(url, ft.LaunchMode.EXTERNAL_APPLICATION)]


async def test_the_address_buttons_keep_their_padding_at_every_text_size(
    show: Show,
) -> None:
    """Directions and Copy address pin M3's padding for a button with an icon (D-344).

    The tonal Directions also stays flat: with a style, Flet lifts it to its
    `elevation`, 1 unless it is set to 0.
    """
    page = await show()
    for identifier in ("venue.directions", "venue.copy_address"):
        button = cast(ft.Button, page.node(identifier).content)
        assert button.style is not None
        assert button.style.padding == ICON_PADDING
    directions = page.node("venue.directions").content
    assert isinstance(directions, ft.FilledTonalButton)
    assert directions.elevation == 0


async def test_directions_whose_launch_raises_say_so(show: Show) -> None:
    """A launch that raises says "Couldn't open the link" (D-182).

    A launcher that returns `false` says nothing: the pin drops the result (U79).
    """
    page = await show()
    page.launcher.error = RuntimeError("no maps app")
    await page.click(cast(ft.Control, page.node("venue.directions").content))
    assert snack_texts(page) == ["Couldn't open the link"]


async def test_copy_address_copies_it_and_says_so_once(show: Show) -> None:
    """Copy address puts the address on the clipboard: one SnackBar."""
    page = await show()
    await page.click(cast(ft.Control, page.node("venue.copy_address").content))
    clipboard = cast(MemoryClipboard, page.services.clipboard)
    assert clipboard.value == "300 E Ocean Blvd, Long Beach, CA 90802"
    assert snack_texts(page) == ["Address copied"]


async def test_a_failed_copy_says_so_and_logs_no_address(
    show: Show, caplog: pytest.LogCaptureFixture
) -> None:
    """A clipboard that fails says so; the log names what, never the address."""
    page = await show()
    clipboard = cast(MemoryClipboard, page.services.clipboard)
    clipboard.error = TimeoutError("timed out setting 300 E Ocean Blvd")
    with caplog.at_level(logging.WARNING):
        await page.click(cast(ft.Control, page.node("venue.copy_address").content))
    assert snack_texts(page) == ["Couldn't copy the address"]
    assert "Ocean" not in caplog.text


async def test_the_zone_note_shows_while_the_device_s_zone_differs(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-240: with the device on another offset, a line says the hours' zone."""
    monkeypatch.setattr(
        screen, "zone_note", lambda *_, **__: "Times are Pacific Time (PDT)"
    )
    page = await show()
    note = page.node("venue.zone_note")
    assert cast(ft.Text, note.content).value == "Times are Pacific Time (PDT)"


async def test_a_year_without_hours_shows_the_feed_s_block(show: Show) -> None:
    """2025 has no `[[venue_hours]]`: over a feed with the block, the page shows it."""
    page = await show(year=2025, feed=2026)
    assert page.nodes("venue.feed")
    assert not page.nodes(REGISTRATION) and not page.nodes("venue.empty")


async def test_without_hours_or_a_feed_block_the_page_sends_to_the_desk(
    show: Show,
) -> None:
    """2025's own feed has no `venues-hours` block: the empty state names the way out."""
    page = await show(year=2025, feed=2025)
    assert page.nodes("venue.empty")
    assert "information desk" in screen.NO_VENUE_BODY


async def test_each_service_with_a_pin_ends_with_its_location_card(
    show: Show,
) -> None:
    """INFO-12, MAP-09: a card per pinned service; Luggage check has none."""
    page = await show()
    labels = {str(node.identifier): node.label for node in page.nodes("venue.service.")}
    assert {
        key: label for key, label in labels.items() if key.endswith(".location")
    } == {
        "venue.service.registration.location": (
            "Show Registration on the Concourse level floor plan"
        ),
        "venue.service.information_desk.location": (
            "Show Information desk on the Concourse level floor plan"
        ),
        "venue.service.swag_pickup.location": (
            "Show Swag pickup on the Arena & exhibit halls floor plan"
        ),
        "venue.service.quiet_room.location": (
            "Show Quiet room on the Concourse level floor plan"
        ),
        "venue.service.lost_found.location": (
            "Show Lost & found on the Upper level floor plan"
        ),
    }


async def test_a_service_s_card_pushes_the_floor_viewer_at_its_pin(
    show: Show,
) -> None:
    """The tap pushes `plan/<plan>?pin=<key>` on Venue & hours' View."""
    page = await show()
    tap = page.node("venue.service.swag_pickup.location").parent
    assert isinstance(tap, ft.Container) and tap.on_click is not None
    await page.click(tap)
    assert page.went == [f"{VIEW}/plan/arena?pin=swag-pickup"]


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_live_reads_at_aa_on_the_card(dark: bool) -> None:
    """The outlined card's fill is the surface, where `live` reads at 4.5:1 (D-33)."""
    live = theme.build_tokens(dark=dark, high_contrast=False).live
    surface = hex_role(scheme(dark), "surface")
    assert contrast_ratio(surface, live) >= 4.5


@pytest.mark.parametrize(
    ("service", "key"),
    [
        ("Registration", "registration"),
        ("Lost & found", "lost_found"),
        ("Information desk", "information_desk"),
    ],
)
def test_service_key_is_lower_case_words_joined_by_underscores(
    service: str, key: str
) -> None:
    """A service's identifier key keeps its letters and digits only."""
    assert screen.service_key(service) == key


def test_directions_url_quotes_the_label() -> None:
    """A label's spaces and ampersands are quoted, so the link stays one link."""
    point = Directions("A & B", 1.5, -2.25)
    assert screen.directions_url(point, ios=True) == (
        "https://maps.apple.com/?q=A%20%26%20B&ll=1.5,-2.25&dirflg=w"
    )
    assert (
        screen.directions_url(point, ios=False)
        == "geo:1.5,-2.25?q=1.5,-2.25(A%20%26%20B)"
    )
