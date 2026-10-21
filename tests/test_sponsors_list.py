"""Tests for the Sponsors list (``screens/sponsors.py``; SPON-01, D-37, D-279, #395).

The page runs in a real Flet session (``tests/sessions.py``'s ``showing()``) on the
recorded 2026 feed: 13 levels, 105 sponsors. These tests read the control tree: the
levels' headings, each tier's shape, the one node per sponsor, where a tap goes, the
states without data, and that a re-render with the same feed runs no item body
(D-153). How the tiers look, wrap at 200 % and read to TalkBack and VoiceOver is
checked on devices (the PR).
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.models import Sponsor
from pycon_us.core.sponsors import sponsor_by_slug
from pycon_us.screens import sponsors as screen
from pycon_us.state import Conference
from tests import sessions
from tests.feeds import processed
from tests.sessions import Shown, text_of

YEAR = load_year(2026)
DATA = processed(2026)
SPONSORS = [sponsor for level in DATA.sponsor_levels for sponsor in level.sponsors]
NODE = "sponsors.sponsor."
"""The prefix of a sponsor's semantics identifier."""

VIEW = "/more/sponsors"
"""The page's View path, which a sponsor's detail is pushed on."""


def sponsor(slug: str) -> Sponsor:
    """Return the 2026 sponsor whose slug is ``slug``."""
    found = sponsor_by_slug(DATA, slug)
    assert found is not None
    return found


@dataclass
class Listed(Shown):
    """The Sponsors page, and which item bodies ran."""

    bodies: list[str] = field(default_factory=list)
    """The slugs of the sponsors whose item bodies ran, in order (D-153)."""


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """Render the Sponsors page and record which item bodies ran.

    It takes a ``conference``, the recorded 2026 one by default. Each item body asks
    for its phrase once, so counting the calls counts the bodies (S2).
    """
    phrase = screen.sponsor_phrase

    def counted(item: Sponsor) -> str:
        sessions.current(Listed).bodies.append(item.slug)
        return phrase(item)

    monkeypatch.setattr(screen, "sponsor_phrase", counted)

    async with AsyncExitStack() as stack:

        async def render(conference: Conference | None = None) -> Listed:
            return await stack.enter_async_context(
                sessions.showing(
                    screen.Sponsors,
                    screen,
                    year=YEAR,
                    conference=Conference(data=DATA, source="bundled", version=1)
                    if conference is None
                    else conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    kind=Listed,
                )
            )

        yield render


def item_of(shown: Shown, slug: str) -> ft.MergeSemantics:
    """Return the merged node that holds the sponsor ``slug``'s phrase."""
    node: ft.BaseControl | None = shown.node(f"{NODE}{slug}")
    while node is not None and not isinstance(node, ft.MergeSemantics):
        node = node.parent
    assert isinstance(node, ft.MergeSemantics)
    return node


def plates(control: ft.BaseControl) -> list[ft.Container]:
    """Return the white logo plates under ``control``, in no set order."""
    found: list[ft.Container] = []
    stack: list[Any] = [control]
    while stack:
        node = stack.pop()
        if isinstance(node, ft.Container) and node.bgcolor == ft.Colors.WHITE:
            found.append(node)
        for name in ("content", "controls"):
            child = getattr(node, name, None)
            if isinstance(child, list):
                stack.extend(child)
            elif isinstance(child, ft.BaseControl):
                stack.append(child)
    return found


def inside[T: ft.BaseControl](control: ft.BaseControl, kind: type[T]) -> T | None:
    """Return the nearest ``kind`` that ``control`` is mounted under, or None."""
    node = control.parent
    while node is not None and not isinstance(node, kind):
        node = node.parent
    return node


# ------------------------------------------------------------------ the rules


def test_tiers_go_by_a_levels_place_never_its_name() -> None:
    """The first level gets full-width cards, the next two logo cards, the rest rows."""
    assert [screen.tier_of(position) for position in range(5)] == [
        "feature",
        "logo",
        "logo",
        "tile",
        "tile",
    ]
    assert screen.tier_of(12) == "tile"


def test_a_sponsor_reads_as_its_name_level_and_booth() -> None:
    """One phrase with the level, which the heading above it does not say with it."""
    assert screen.sponsor_phrase(sponsor("bloomberg")) == (
        "Bloomberg, Visionary sponsor, booth 613"
    )
    assert screen.sponsor_phrase(sponsor("nvidia")) == "NVIDIA, Visionary sponsor"
    assert screen.booth_line(sponsor("bloomberg")) == "Booth 613"
    assert screen.booth_line(sponsor("nvidia")) is None


def test_a_row_outside_its_level_says_the_level_with_the_booth() -> None:
    """Search's rows have no level heading, so their line says it (#397)."""
    assert (
        screen.level_line(sponsor("bloomberg")) == "Visionary \N{MIDDLE DOT} Booth 613"
    )
    assert screen.level_line(sponsor("nvidia")) == "Visionary"


# ------------------------------------------------------------------ the page


async def test_2026_has_a_level_two_heading_per_level_in_order(show: Any) -> None:
    """13 sections in ``level_order``, from Visionary to Community, after the intro."""
    shown = await show()
    headings = [
        text_of(node)
        for node in shown.find(ft.Semantics)
        if node.header and node.heading_level == 2
    ]
    assert sorted(headings) == sorted(level.name for level in DATA.sponsor_levels)
    assert len(headings) == 13
    assert screen.INTRO in shown.texts()
    body = shown.find(ft.ListView)[0].controls
    order = [text_of(c) for c in body if isinstance(c, ft.Semantics) and c.header]
    assert order == [level.name for level in DATA.sponsor_levels]


async def test_every_sponsor_is_one_button_node_in_feed_order(show: Any) -> None:
    """105 nodes, each a button read as its phrase, its texts and plate left out."""
    shown = await show()
    nodes = shown.nodes(NODE)
    assert sorted(str(n.identifier) for n in nodes) == sorted(
        f"{NODE}{s.slug}" for s in SPONSORS
    )
    assert shown.bodies == [s.slug for s in SPONSORS]
    bloomberg = shown.node(f"{NODE}bloomberg")
    assert bloomberg.label == "Bloomberg, Visionary sponsor, booth 613"
    assert bloomberg.button is True
    assert bloomberg.exclude_semantics is True
    assert "Booth 613" in shown.texts()


async def test_visionary_sponsors_are_full_width_cards_with_a_wide_plate(
    show: Any,
) -> None:
    """The 7 Visionary sponsors: cards in the list itself, a 96 dp plate as wide as each."""
    shown = await show()
    visionary = DATA.sponsor_levels[0]
    assert len(visionary.sponsors) == 7
    for item in visionary.sponsors:
        merged = item_of(shown, item.slug)
        assert isinstance(merged.content, ft.Card)
        assert inside(merged, ft.ResponsiveRow) is None
        (plate,) = plates(merged)
        assert plate.height == screen.FEATURE_PLATE
        assert plate.width is None  # the card's width (D-279)


async def test_the_next_two_levels_are_logo_cards_sharing_a_responsive_row(
    show: Any,
) -> None:
    """Sustainability and Maintaining: cards two to a phone's row, more on a wider one."""
    shown = await show()
    sustainability, maintaining = DATA.sponsor_levels[1:3]
    assert [sustainability.name, maintaining.name] == ["Sustainability", "Maintaining"]
    for level in (sustainability, maintaining):
        row = None
        for item in level.sponsors:
            merged = item_of(shown, item.slug)
            assert isinstance(merged.content, ft.Card)
            assert merged.col == screen.LOGO_COLUMNS
            row = row or inside(merged, ft.ResponsiveRow)
            assert inside(merged, ft.ResponsiveRow) is row is not None
            (plate,) = plates(merged)
            assert plate.height == screen.LOGO_PLATE
            assert plate.width is None


async def test_the_other_levels_are_rows_with_a_48_dp_plate(show: Any) -> None:
    """Every level from Contributing on: rows, no cards, a square 48 dp plate."""
    shown = await show()
    for level in DATA.sponsor_levels[3:]:
        for item in level.sponsors:
            merged = item_of(shown, item.slug)
            assert isinstance(merged.content, ft.Container)
            assert inside(merged, ft.Card) is None
            (plate,) = plates(merged)
            assert plate.width == plate.height == screen.TILE_PLATE


async def test_every_logo_falls_back_to_initials_on_a_plate_of_fixed_height(
    show: Any,
) -> None:
    """Offline without a logo cache each logo shows initials; no plate's height moves."""
    shown = await show()
    for item in SPONSORS:
        (plate,) = plates(item_of(shown, item.slug))
        assert plate.height is not None
        image = plate.content
        assert isinstance(image, ft.Image), item.name  # every 2026 sponsor has a logo
        assert isinstance(image.error_content, ft.CircleAvatar)


async def test_a_tap_pushes_the_sponsors_detail_on_this_view(show: Any) -> None:
    """A card or a row pushes ``…/sponsor/<slug>``, one drill level (D-17)."""
    shown = await show()
    for slug in ("bloomberg", "microsoft", "sentinelone"):
        tapped = item_of(shown, slug).content
        assert isinstance(tapped, ft.Card | ft.Container)
        target = tapped.content if isinstance(tapped, ft.Card) else tapped
        assert isinstance(target, ft.Container)
        await shown.click(target)
    assert shown.went == [
        f"{VIEW}/sponsor/bloomberg",
        f"{VIEW}/sponsor/microsoft",
        f"{VIEW}/sponsor/sentinelone",
    ]


async def test_a_re_render_with_the_same_feed_runs_no_item_body(show: Any) -> None:
    """D-153: a failed refresh re-renders the page, never its 105 items."""
    conference = Conference(data=DATA, source="bundled", version=1)
    shown = await show(conference)
    shown.bodies.clear()
    conference.problem = "offline"
    await shown.settle()
    assert shown.bodies == []
    assert any(text.startswith("Offline") for text in shown.texts())  # the strip


# ------------------------------------------------------------------ the states


async def test_without_data_the_page_loads_then_offers_to_try_again(
    show: Any,
) -> None:
    """ux.md §4.1: the strip and the skeleton, then the way out once a fetch failed."""
    loading = await show(Conference())
    assert loading.nodes("app.status")
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(Conference(problem="offline"))
    assert failed.node("sponsors.no_data").live_region
    assert [b.content for b in failed.find(ft.FilledTonalButton)] == ["Try again"]


async def test_a_feed_without_sponsors_says_none_are_announced(show: Any) -> None:
    """A new §4.6 row: "No sponsors announced yet", no button, no intro."""
    empty = replace(DATA, sponsor_levels=())
    shown = await show(Conference(data=empty, source="bundled", version=1))
    assert shown.node("sponsors.empty").live_region
    assert "No sponsors announced yet" in shown.texts()
    assert screen.INTRO not in shown.texts()
    assert shown.find(ft.FilledTonalButton) == []
    assert shown.nodes(NODE) == []
