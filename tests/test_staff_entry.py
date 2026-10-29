"""Tests for the ways into the staff tools: More's section and Now's card (#725).

SHELL-06, SHELL-07, SHELL-11, AUTH-05; D-16, D-169, D-421. More and Now run in a real
Flet session (``tests/harness.py``, ``tests/now_view.py``) signed in as each seeded
mock account, so the section and the card come and go as the ``Account`` store's
flags change, and the counts follow the ``Staff`` store.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us.account import Account
from pycon_us.account_profile import FLAGS
from pycon_us.config import load_year
from pycon_us.core.staff_tools import BUILT_TOOLS, TOOLS
from pycon_us.locations import PAGES, parent_of
from pycon_us.memory import ViewMemory
from pycon_us.prefs import DEV_MOCK_API_URL, Prefs
from pycon_us.screens import more
from pycon_us.screens.more import More
from pycon_us.screens.staff_entry import CARD
from pycon_us.staff import Staff
from pycon_us.state import Conference
from tests import now_view
from tests.api_clients import BASE_URL
from tests.harness import Shown, showing
from tests.now_view import _children, may
from tests.test_more import outline

data, render = (now_view.data, now_view.render)

SEED = Path(__file__).parent / "fixtures" / "mock" / "seed.json"

ROLES = ("attendee", "speaker", "sponsor", "staff", "coc", "all")
"""The seeded mock accounts, by role."""

BUILT_ROWS = {
    "attendee": [],
    "speaker": [],
    "sponsor": ["more.staff.lead"],
    "staff": ["more.staff.lead", "more.staff.swag"],
    "coc": ["more.staff.coc"],
    "all": ["more.staff.coc", "more.staff.lead", "more.staff.swag"],  # sorted
}
"""Each role's rows of built tools: the Lead scanner (``lead_retrieval or door_check``),
Swag pickup (``door_check``, #769) and CoC incident (``mask_violation``, #760); Door
check waits for its admission (D-169)."""


def seeded(role: str) -> Account:
    """A restored ``Account`` signed in as the mock's seeded account of ``role``."""
    (seed,) = [a for a in json.loads(SEED.read_text())["accounts"] if a["role"] == role]
    flags = {FLAGS[name]: value for name, value in seed["features"].items()}
    return Account(
        restored=True,
        signed_in=True,
        email=seed["email"],
        nickname=seed["nickname"],
        **flags,
    )


def mock_prefs(*, mock_url: bool = True) -> Prefs:
    """Loaded prefs, with the mock's URL set unless ``mock_url`` is False (D-51)."""
    prefs = Prefs(loaded=True)
    if mock_url:
        prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
    return prefs


type ShowMore = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ShowMore]:
    """Return a function that renders More for an account, a URL and a ``Staff``."""
    async with AsyncExitStack() as stack:

        async def render_more(
            account: Account,
            *,
            mock_url: bool = True,
            staff: Staff | None = None,
        ) -> Shown:
            """Render More signed in as ``account``, with or without a mock URL."""
            return await stack.enter_async_context(
                showing(
                    More,
                    more,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="/more",
                    prefs=mock_prefs(mock_url=mock_url),
                    account=account,
                    staff=staff,
                )
            )

        yield render_more


def staff_rows(shown: Shown) -> list[str]:
    """The identifiers of More's staff rows on screen, sorted."""
    return sorted(str(node.identifier) for node in shown.nodes("more.staff."))


def tile(node: ft.Semantics) -> ft.ListTile:
    """The ``ListTile`` a ``LinkTile``'s identifier node holds."""
    assert isinstance(node.content, ft.ListTile)
    return node.content


def second_line(node: ft.Semantics) -> tuple[str, str]:
    """A row's second line as shown and as read: " · " is read as a pause."""
    line = tile(node).subtitle
    assert isinstance(line, ft.Text)
    return str(line.value), str(line.semantics_label)


@pytest.mark.parametrize("role", ROLES)
async def test_more_lists_the_built_tools_of_each_mock_account(
    show_more: ShowMore, role: str
) -> None:
    """Each seeded role gets exactly its built tools' rows on More (``BUILT_ROWS``)."""
    shown = await show_more(seeded(role))
    expected = BUILT_ROWS[role]
    assert staff_rows(shown) == expected
    assert ("Staff tools" in shown.texts()) is bool(expected)


async def test_the_lead_scanner_row_says_its_purpose_and_opens_its_route(
    show_more: ShowMore,
) -> None:
    """Its row reads its purpose and pushes ``/more/staff/lead``; Back returns to More."""
    shown = await show_more(seeded("sponsor"))
    node = shown.node("more.staff.lead")
    assert tile(node).title == "Lead scanner"
    assert second_line(node) == ("Capture leads at your booth",) * 2
    await shown.click(tile(node))
    assert shown.went == ["/more/staff/lead"]
    assert parent_of("/more/staff/lead") == "/more"  # Back returns to More


async def test_the_section_comes_right_under_the_profile_row(
    show_more: ShowMore,
) -> None:
    """The profile row, then "Staff tools" and its rows in O-7's order (ux.md §2.2)."""
    shown = await show_more(seeded("all"))
    (body,) = shown.find(ft.ListView)
    assert outline(list(body.controls[:6])) == [
        "Robin Everything",  # the profile row, signed in
        "# Staff tools",
        "Lead scanner",
        "Swag pickup",
        "CoC incident",
        "# Programme",
    ]


async def test_no_mock_url_or_signed_out_shows_no_staff_rows(
    show_more: ShowMore,
) -> None:
    """Without a mock URL (D-51), or signed out, nothing is listed."""
    assert staff_rows(await show_more(seeded("all"), mock_url=False)) == []
    assert staff_rows(await show_more(Account(restored=True))) == []


async def test_the_lead_scanner_row_says_the_outbox_counts_until_they_sync(
    show_more: ShowMore,
) -> None:
    """With queued rows it says "3 pending · 1 failed"; after a sync, the words go."""
    staff = Staff(pending=3, failed=1)
    shown = await show_more(seeded("sponsor"), staff=staff)
    assert second_line(shown.node("more.staff.lead")) == (
        "Capture leads at your booth · 3 pending · 1 failed",
        "Capture leads at your booth, 3 pending, 1 failed",
    )
    staff.pending = staff.failed = 0  # a sync pass reports
    await shown.settle()
    assert second_line(shown.node("more.staff.lead"))[0] == (
        "Capture leads at your booth"
    )


async def test_the_section_follows_sign_out_sign_in_and_a_flag_change(
    show_more: ShowMore,
) -> None:
    """Signing out removes it, signing in adds it, a lost flag removes it: live."""
    account = seeded("sponsor")
    shown = await show_more(account)
    account.signed_in = False
    await shown.settle()
    assert staff_rows(shown) == []
    account.signed_in = True
    await shown.settle()
    assert staff_rows(shown) == ["more.staff.lead"]
    account.lead_retrieval = False  # a flag refresh took the role away (#686)
    await shown.settle()
    assert staff_rows(shown) == []


# ------------------------------------------------------------------ Now's card


async def test_now_shows_the_scan_card_under_the_strip_in_every_season(
    render: Callable[..., Any],
) -> None:
    """Before and during the conference, a sponsor's card says "Lead scanner"."""
    for now in (may(1, 9), may(15, 11, 10)):
        shown = await render(now, prefs=mock_prefs(), account=seeded("sponsor"))
        node = shown.node(CARD)
        assert tile(node).title == "Scan badges"
        assert second_line(node) == ("Lead scanner", "Lead scanner")
        # Under the header and the strip (ux §5.1): its component's body.
        (card,) = _children(shown.body.controls[2])
        assert isinstance(card, ft.Card) and card.variant == ft.CardVariant.FILLED


@pytest.mark.parametrize("role", ROLES)
async def test_the_card_shows_for_the_accounts_with_a_built_tool(
    render: Callable[..., Any], role: str
) -> None:
    """The sponsor, staff, coc and all accounts get the card; the others don't."""
    shown = await render(may(15, 11, 10), prefs=mock_prefs(), account=seeded(role))
    assert shown.has(CARD) is bool(BUILT_ROWS[role])


async def test_no_card_without_a_mock_url(render: Callable[..., Any]) -> None:
    """Without a mock URL there is no staff entry at all (D-51)."""
    shown = await render(
        may(15, 11, 10), prefs=mock_prefs(mock_url=False), account=seeded("all")
    )
    assert not shown.has(CARD)


async def test_the_card_pushes_the_tool_under_now_so_back_returns_there(
    render: Callable[..., Any],
) -> None:
    """A tap pushes ``/now/staff/lead``, whose parent is Now (D-421)."""
    shown = await render(may(15, 11, 10), prefs=mock_prefs(), account=seeded("staff"))
    await shown.click(tile(shown.node(CARD)))
    assert shown.went == ["/now/staff/lead"]
    assert "/now/staff/lead" in PAGES
    assert parent_of("/now/staff/lead") == "/now"


async def test_the_card_says_the_counts_and_goes_with_a_sign_out(
    render: Callable[..., Any],
) -> None:
    """The card says "Lead scanner · 3 pending", and goes and comes back with the account."""
    account = seeded("sponsor")
    shown = await render(
        may(15, 11, 10), prefs=mock_prefs(), account=account, staff=Staff(pending=3)
    )
    assert second_line(shown.node(CARD)) == (
        "Lead scanner · 3 pending",
        "Lead scanner, 3 pending",
    )
    account.signed_in = False
    await shown.settle()
    assert not shown.has(CARD)
    account.signed_in = True  # a sign-in brings it back without a restart
    await shown.settle()
    assert shown.has(CARD)


async def test_the_card_opens_the_last_tool_opened_while_it_is_allowed(
    render: Callable[..., Any],
) -> None:
    """A remembered tool the account may not open falls back to the first entry."""
    memory = ViewMemory(staff_tool="coc")  # built, but not this account's
    shown = await render(
        may(15, 11, 10), prefs=mock_prefs(), account=seeded("sponsor"), memory=memory
    )
    await shown.click(tile(shown.node(CARD)))
    assert shown.went == ["/now/staff/lead"]


async def test_the_swag_pickup_row_says_its_purpose_and_opens_its_route(
    show_more: ShowMore,
) -> None:
    """Staff get "Swag pickup", which pushes ``/more/staff/swag``; a sponsor doesn't."""
    shown = await show_more(seeded("staff"))
    node = shown.node("more.staff.swag")
    assert tile(node).title == "Swag pickup"
    assert second_line(node) == ("Hand out swag at pickup",) * 2  # no counts (D-56)
    await shown.click(tile(node))
    assert shown.went == ["/more/staff/swag"]
    assert not (await show_more(seeded("sponsor"))).nodes("more.staff.swag")


async def test_the_card_opens_swag_pickup_when_it_was_the_last_tool(
    render: Callable[..., Any],
) -> None:
    """Staff who last opened Swag pickup get it from Now's card, under Now (D-421)."""
    shown = await render(
        may(15, 11, 10),
        prefs=mock_prefs(),
        account=seeded("staff"),
        memory=ViewMemory(staff_tool="swag"),
    )
    assert second_line(shown.node(CARD))[0] == "Swag pickup"
    await shown.click(tile(shown.node(CARD)))
    assert shown.went == ["/now/staff/swag"]


def test_every_built_tool_has_its_route_under_more_and_under_now() -> None:
    """A tool in ``BUILT_TOOLS`` is a page at both entries, so no entry is dead."""
    for tool in TOOLS:
        if tool.key in BUILT_TOOLS:
            assert {tool.route, tool.now_route} <= PAGES
