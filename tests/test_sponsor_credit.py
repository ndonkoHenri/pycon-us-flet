"""Tests for the sponsor credits (`screens/sponsor_credit.py`; #417, D-37, D-337).

INFO-09, MAP-10: who provides the Wi-Fi and the quiet room is year data, a sponsor slug
checked against the snapshot, credited on the Wi-Fi page, Venue & hours' Quiet room
card and Help & safety's Quiet room line by a row that pushes the sponsor's detail. The
pages run in a real Flet session (`tests/sessions.py`); the snapshot tool's check is
in `tests/test_update_snapshot.py`. How the rows look and read is checked on devices.
"""

import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import flet as ft
import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year
from pycon_us.core.models import ConferenceData
from pycon_us.core.sponsors import sponsor_by_slug
from pycon_us.locations import parent_of
from pycon_us.screens import help as help_screen
from pycon_us.screens import venue, wifi
from pycon_us.state import Conference
from tests.feeds import processed
from tests.harness import Shown, showing

CREDITS = load_year(2026).content.sponsor_credits

type Show = Callable[..., Awaitable[Shown]]

PAGES = [
    (wifi.Wifi, wifi, "/more/wifi", "wifi.sponsor", "Wi-Fi provided by Temporal"),
    (
        venue.Venue,
        venue,
        "/more/venue",
        "venue.service.quiet_room.sponsor",
        "Quiet room provided by Google",
    ),
    (
        help_screen.Help,
        help_screen,
        "/more/help",
        "help.quiet_room.sponsor",
        "Quiet room provided by Google",
    ),
]
"""Each credited page: its screen, its module, its View, the row's node, its title."""


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders a page over 2026's data and a feed, or none."""
    async with AsyncExitStack() as stack:

        async def render(
            screen: Callable[[], ft.Control],
            module: ModuleType,
            view: str,
            data: ConferenceData | None,
        ) -> Shown:
            """Render `screen` at `view` over `data` (None: no feed yet)."""
            conference = (
                Conference()
                if data is None
                else Conference(data=data, source="bundled", version=1)
            )
            return await stack.enter_async_context(
                showing(
                    screen,
                    module,
                    year=load_year(2026),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=view,
                )
            )

        yield render


def without(data: ConferenceData, slug: str) -> ConferenceData:
    """The feed with the sponsor `slug` taken out of its levels."""
    levels = tuple(
        replace(level, sponsors=tuple(s for s in level.sponsors if s.slug != slug))
        for level in data.sponsor_levels
    )
    return replace(data, sponsor_levels=levels)


def test_2026_credits_temporal_for_wifi_and_google_for_the_quiet_room() -> None:
    """Each 2026 credit names its sponsor by slug, with a public source and a date."""
    data = processed(2026)
    for key, slug in (("wifi", "temporal"), ("quiet_room", "google")):
        credit = getattr(CREDITS, key)
        assert credit is not None and credit.slug == slug
        assert credit.source.startswith("https://") and credit.checked
        assert sponsor_by_slug(data, slug) is not None


def test_the_loader_refuses_a_credit_whose_sponsor_the_snapshot_lacks(
    tmp_path: Path,
) -> None:
    """An unknown slug fails the session check, naming the credit (D-337)."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "2026" / "content.toml"
    text = path.read_text(encoding="utf-8")
    assert 'slug = "temporal"' in text
    path.write_text(text.replace('slug = "temporal"', 'slug = "temporl"'), "utf-8")
    assert load_year(2026, tmp_path).content.sponsor_credits.wifi  # the app loads it
    with pytest.raises(YearDataError) as error:
        load_year(2026, tmp_path, check_sessions=True)
    assert str(error.value) == (
        "2026/content.toml: sponsor_credits.wifi.slug: 'temporl' is not a sponsor "
        "of the year's feed"
    )


def test_the_loader_refuses_a_credit_without_an_https_source(tmp_path: Path) -> None:
    """A credit's source is a public `https` page, as a safety contact's is."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "2026" / "content.toml"
    text = path.read_text(encoding="utf-8")
    old = 'source = "https://github.com/PyCon/pycon-us-mobile/blob/main/src/app/pages/wifi'
    assert old in text
    path.write_text(text.replace(old, old.replace("https", "http")), "utf-8")
    with pytest.raises(YearDataError, match=r"sponsor_credits\.wifi\.source"):
        load_year(2026, tmp_path)


@pytest.mark.parametrize(("screen", "module", "view", "identifier", "title"), PAGES)
async def test_a_credit_reads_as_one_phrase_and_pushes_the_sponsor(
    show: Show,
    screen: Callable[[], ft.Control],
    module: ModuleType,
    view: str,
    identifier: str,
    title: str,
) -> None:
    """The row says who provides it, and a tap pushes their detail over the page."""
    page = await show(screen, module, view, processed(2026))
    slug = "temporal" if "Wi-Fi" in title else "google"
    sponsor = sponsor_by_slug(processed(2026), slug)
    assert sponsor is not None
    tile = page.node(identifier).content
    assert isinstance(tile, ft.ListTile)  # one merged node: the title, then the level
    assert (tile.title, tile.subtitle) == (title, f"{sponsor.level} sponsor")
    await page.click(tile)
    assert page.went == [f"{view}/sponsor/{slug}"]
    assert parent_of(page.went[0]) == view  # Back returns to the page


@pytest.mark.parametrize(("screen", "module", "view", "identifier", "title"), PAGES)
async def test_a_feed_without_the_sponsor_hides_the_credit(
    show: Show,
    screen: Callable[[], ft.Control],
    module: ModuleType,
    view: str,
    identifier: str,
    title: str,
) -> None:
    """A newer feed that drops the sponsor shows no credit, which would lead nowhere."""
    slug = "temporal" if "Wi-Fi" in title else "google"
    page = await show(screen, module, view, without(processed(2026), slug))
    assert not page.nodes(identifier)
    assert title not in [c.title for c in page.find(ft.ListTile)]


async def test_without_a_feed_there_is_no_credit(show: Show) -> None:
    """Before the first feed, the Wi-Fi page shows its values and no credit."""
    page = await show(wifi.Wifi, wifi, "/more/wifi", None)
    assert page.nodes("wifi.password")
    assert not page.nodes("wifi.sponsor")


async def test_only_the_quiet_room_s_card_carries_the_credit(show: Show) -> None:
    """Venue & hours credits Google once, on the Quiet room's card alone."""
    page = await show(venue.Venue, venue, "/more/venue", processed(2026))
    titles = [c.title for c in page.find(ft.ListTile)]
    assert titles.count("Quiet room provided by Google") == 1
