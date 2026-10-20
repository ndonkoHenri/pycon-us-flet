"""Tests for the Job listings page (``screens/jobs.py``; SPON-06, SPON-08, #399).

The page runs in a real Flet session (``tests/sessions.py``'s ``showing()``) on the
recorded 2026 feed: 13 listings, Bloomberg's with 15 roles, SerpApi's and marimo's
long form, OpenEDG's a placeholder. The roles come from ``core/jobs.py``, tested in
``tests/test_jobs.py``; these tests read what the page makes of them. How the cards
look, wrap at 200 % and read to TalkBack and VoiceOver is checked on devices (the PR).
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.config import load_year
from pycon_us.core.jobs import sponsor_of
from pycon_us.core.models import JobListing
from pycon_us.core.sprints import needs_more
from pycon_us.locations import parent_of
from pycon_us.screens import jobs as screen
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import sessions
from tests.fakes import MemoryPrefs
from tests.feeds import processed, recorded
from tests.sessions import Shown

YEAR = load_year(2026)
DATA = processed(2026)
VIEW = "/more/jobs"
"""The page's View path, which a sponsor's detail is pushed on."""

CARD = "jobs.listing."
"""The prefix of a card header's semantics identifier."""


def listing(name: str) -> JobListing:
    """Return the 2026 listing of the sponsor named ``name``."""
    (found,) = [j for j in DATA.job_listings if j.sponsor_name == name]
    return found


def role_ids(shown: Shown, item: JobListing) -> list[str]:
    """The identifiers of a card's role rows, in the rows' order."""
    prefix = f"jobs.role.{item.id}."
    ids = [str(n.identifier) for n in shown.nodes(prefix)]
    return sorted(ids, key=lambda i: int(i.removeprefix(prefix)))


def toggle_of(shown: Shown, identifier: str) -> tuple[ft.Semantics, ft.TextButton]:
    """A card's toggle: the node that says its state, and its button."""
    toggle = cast(ft.Semantics, shown.node(identifier).content)
    return toggle, cast(ft.TextButton, toggle.content)


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """Return a function that shows the page, with a ``conference`` (2026 by default)."""
    async with AsyncExitStack() as stack:

        async def render(conference: Conference | None = None) -> Shown:
            return await stack.enter_async_context(
                sessions.showing(
                    screen.Jobs,
                    screen,
                    year=YEAR,
                    conference=conference
                    or Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        yield render


# ------------------------------------------------------------------ the rules


def test_a_listing_s_sponsor_is_the_one_its_name_names() -> None:
    """Every 2026 listing names a sponsor; an unknown name has none."""
    for item in DATA.job_listings:
        found = sponsor_of(DATA, item)
        assert found is not None and found.name == item.sponsor_name
    assert (
        sponsor_of(DATA, replace(listing("Bloomberg"), sponsor_name="Nobody")) is None
    )


def test_needs_more_cuts_long_text_and_markdown_with_breaks_or_links() -> None:
    """D-202's rule, shared with the Sprints cards: length, a line break or a link."""
    assert not needs_more("Short.", "Short.")
    assert needs_more("x" * 161, "x")
    assert needs_more("a b", "a\n\nb")
    assert needs_more("site", "[site](https://example.com)")


# ------------------------------------------------------------------ the cards


async def test_2026_shows_a_card_per_listing_each_header_a_heading(
    show: Any,
) -> None:
    """13 cards in feed order, each header one node: a level-2 heading and a button."""
    shown = await show()
    headers = shown.nodes(CARD)
    assert sorted(str(n.identifier) for n in headers) == sorted(
        f"{CARD}{item.id}" for item in DATA.job_listings
    )
    assert len(shown.find(ft.Card)) == 13
    node = shown.node(f"{CARD}{listing('Bloomberg').id}")
    assert node.label == "Bloomberg, Visionary sponsor"
    assert node.header and node.heading_level == 2
    assert node.button and node.exclude_semantics
    assert isinstance(cast(ft.Control, node.parent).parent, ft.MergeSemantics)


async def test_bloomberg_shows_five_roles_then_all_fifteen(show: Any) -> None:
    """SPON-06: the first five linked roles, "Show all 15 roles", then the rest."""
    shown = await show()
    item = listing("Bloomberg")
    assert role_ids(shown, item) == [f"jobs.role.{item.id}.{i}" for i in range(5)]
    toggle, button = toggle_of(shown, f"jobs.all_roles.{item.id}")
    assert toggle.expanded is False  # said "collapsed"
    assert cast(ft.Text, button.content).value == "Show all 15 roles"
    await shown.click(button)
    assert len(role_ids(shown, item)) == 15
    toggle, button = toggle_of(shown, f"jobs.all_roles.{item.id}")
    assert toggle.expanded is True
    assert cast(ft.Text, button.content).value == "Show fewer roles"


async def test_a_role_is_a_link_to_the_in_app_browser(show: Any) -> None:
    """Each role row opens its page in the in-app browser, read as a link."""
    shown = await show()
    item = listing("Hudson River Trading")
    assert len(role_ids(shown, item)) == 5  # five: no "Show all"
    assert shown.nodes(f"jobs.all_roles.{item.id}") == []
    node = shown.node(f"jobs.role.{item.id}.0")
    assert node.link
    (tile,) = [t for t in shown.find(ft.ListTile) if _under(t, node)]
    assert cast(ft.Icon, tile.leading).icon == ft.Icons.WORK_OUTLINE
    await shown.click(tile)
    assert shown.launcher.launched == [
        (item.roles[0].url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


async def test_the_header_pushes_the_sponsor_on_this_page(show: Any) -> None:
    """D-17: ``/more/jobs/sponsor/<slug>``, whose Back returns to the list."""
    shown = await show()
    node = shown.node(f"{CARD}{listing('Bloomberg').id}")
    await shown.click(cast(ft.Control, node.parent))
    assert shown.went == ["/more/jobs/sponsor/bloomberg"]
    assert parent_of(shown.went[0]) == VIEW


async def test_a_listing_without_its_sponsor_links_nowhere(show: Any) -> None:
    """A name the levels lack: no button, no chevron, nothing pushed."""
    lost = replace(listing("Bloomberg"), sponsor_name="Nobody")
    data = replace(DATA, job_listings=(lost,))
    shown = await show(Conference(data=data, source="bundled", version=1))
    node = shown.node(f"{CARD}{lost.id}")
    assert not node.button
    assert [i for i in shown.find(ft.Icon) if i.icon == ft.Icons.CHEVRON_RIGHT] == []


async def test_a_long_form_listing_is_cut_with_more(show: Any) -> None:
    """D-202: four lines and "More", which shows the whole Markdown."""
    shown = await show()
    item = listing("SerpApi")
    assert role_ids(shown, item) == []
    assert [t.max_lines for t in shown.find(ft.Text) if t.max_lines] == [4, 4]
    assert shown.find(ft.Markdown) == []  # SerpApi's and marimo's, both cut
    toggle, button = toggle_of(shown, f"jobs.more.{item.id}")
    assert toggle.expanded is False
    assert cast(ft.Text, button.content).value == "More"
    assert cast(ft.Text, button.content).semantics_label == (
        "More about SerpApi's listing"
    )
    await shown.click(button)
    markdown = [m.value for m in shown.find(ft.Markdown)]
    assert markdown == [item.description_md]


async def test_a_placeholder_says_no_roles(show: Any) -> None:
    """OpenEDG's "N/A": its header, then "No roles listed", no Markdown."""
    data = replace(DATA, job_listings=(listing("OpenEDG Python Institute"),))
    shown = await show(Conference(data=data, source="bundled", version=1))
    assert screen.NO_ROLES in shown.texts()
    assert shown.find(ft.Markdown) == []


# ------------------------------------------------------------------ the states


async def test_a_year_without_listings_says_so(show: Any) -> None:
    """2025's feed has none: "No job listings yet", no button (D-175)."""
    data = replace(DATA, job_listings=())
    shown = await show(Conference(data=data, source="bundled", version=1))
    assert shown.node("jobs.empty").live_region
    assert "No job listings yet" in shown.texts()
    assert shown.find(ft.FilledTonalButton) == []


async def test_without_data_the_page_loads_then_offers_to_try_again(
    show: Any,
) -> None:
    """ux.md §4.1: the skeleton until the first fetch has failed, then the way out."""
    loading = await show(Conference())
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(Conference(problem="offline"))
    assert failed.node("jobs.no_data").live_region


async def test_a_failed_refresh_offline_keeps_the_listings_and_the_schedule(
    show: Any, tmp_path: Path
) -> None:
    """SPON-08, D-145: Ionic's refresh wiped the schedule cache; ours never does."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    assert await storage.write_feed(recorded(2026))
    conference = Conference()
    await conference.load_local(storage, YEAR)
    shown = await show(conference)
    assert len(shown.nodes(CARD)) == 13

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    await conference.refresh(storage, YEAR, transport=httpx.MockTransport(offline))
    await shown.settle()

    assert conference.problem == "offline"
    assert len(shown.nodes(CARD)) == 13
    assert conference.data is not None and conference.data.sessions
    assert storage.feed_path.read_bytes() == recorded(2026)


def _under(control: ft.BaseControl, ancestor: ft.BaseControl) -> bool:
    """Return whether ``control`` is mounted under ``ancestor``."""
    node = control.parent
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False
