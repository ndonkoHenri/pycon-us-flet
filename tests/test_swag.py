"""Tests for Swag pickup's lookup, ``swag.py`` (SHIRT-02, API-06; ux.md §7.3).

Each row of the issue's table against the mock's real transport, signed in as the
seeded staff account (Ada: 2 T-shirts and a bag; Grace: 1 T-shirt; Margaret: nothing),
or a fixed ``httpx.MockTransport`` reply: items left, all picked up, nothing bought, an
unknown badge, no connection and another failure. Nothing is ever queued (D-56).
"""

import httpx
import pytest

from pycon_us.check_in_api import fetch_catalog, redeem
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.check_in import Category, redeem_payload, swag_catalog
from pycon_us.services.api import ApiClient
from pycon_us.swag import (
    ALREADY,
    NEEDS_CONNECTION,
    NO_CONNECTION,
    NOT_CHECKED,
    NOT_FOUND,
    NOTHING,
    READY,
    look_up,
    spoken_list,
)
from tests.api_clients import client_for, replying, signed_in

SHIRT = Category(3, "T-Shirt")
BAG = Category(4, "Swag Bag")
BOTH = (SHIRT, BAG)
"""The seed's two swag categories."""


def badge(n: int) -> Badge:
    """Return the seeded attendee ``MOCK000n``'s badge, as ``parse_badge`` reads it."""
    return Badge(f"MOCK000{n}", f"v4l1d0{n}", f"v4l1d0{n}")


async def staff_client() -> ApiClient:
    """Return a client signed in to a freshly seeded mock as the staff account."""
    client, _, _ = await signed_in("staff")
    return client


async def test_the_seeded_swag_categories_are_the_shirt_and_the_bag() -> None:
    """The fixed categories here are what the screen's chips come from."""
    client = await staff_client()
    assert swag_catalog(await fetch_catalog(client)).categories == BOTH
    await client.aclose()


async def test_items_left_are_ready_to_hand_out_one_line_each() -> None:
    """Ada: accepted, her name, "1× Swag Bag" and "2× T-Shirt (M)" (by category)."""
    client = await staff_client()
    result = await look_up(client, badge(1), categories=BOTH)
    assert result == ScanResult(
        ScanOutcome.ACCEPTED,
        READY,
        "Ada Example",
        ("1× Swag Bag", "2× T-Shirt (M)"),
        "MOCK0001",
    )
    await client.aclose()


async def test_only_the_categories_chosen_are_asked_about() -> None:
    """Grace with T-shirts only: her one T-shirt; Ada with the bag only: the bag."""
    client = await staff_client()
    grace = await look_up(client, badge(2), categories=(SHIRT,))
    assert (grace.word, grace.title, grace.details) == (
        READY,
        "Grace Sample",
        ("1× T-Shirt (L)",),
    )
    ada = await look_up(client, badge(1), categories=(BAG,))
    assert ada.details == ("1× Swag Bag",)
    await client.aclose()


async def test_everything_picked_up_is_a_duplicate() -> None:
    """Once Ada's items are redeemed, a scan says "Already picked up" with her name."""
    client = await staff_client()
    payload = redeem_payload("MOCK0001", None, 1.0, {30: 2, 40: 1}, swag=True)
    await redeem(client, payload)
    result = await look_up(client, badge(1), categories=BOTH)
    assert result == ScanResult(
        ScanOutcome.DUPLICATE, ALREADY, "Ada Example", (), "MOCK0001"
    )
    await client.aclose()


async def test_nothing_bought_is_denied_naming_the_categories() -> None:
    """Margaret bought nothing: "Nothing to pick up", her name and what was checked."""
    client = await staff_client()
    result = await look_up(client, badge(4), categories=BOTH)
    assert result == ScanResult(
        ScanOutcome.DENIED,
        NOTHING,
        "Margaret Test",
        ("None bought in T-Shirt or Swag Bag.",),
        "MOCK0004",
    )
    await client.aclose()


async def test_an_unknown_badge_is_not_found_with_the_server_s_message() -> None:
    """A 404: "Badge not found", the code and the mock's own message."""
    client = await staff_client()
    result = await look_up(client, Badge("NOBODY", "x", "x"), categories=BOTH)
    assert (result.outcome, result.word, result.title) == (
        ScanOutcome.DENIED,
        NOT_FOUND,
        "NOBODY",
    )
    assert len(result.details) == 1 and result.details[0]
    await client.aclose()


def offline(request: httpx.Request) -> httpx.Response:
    """Answer nothing: the connection fails, as in airplane mode."""
    raise httpx.ConnectError("offline", request=request)


@pytest.mark.parametrize("api", ["offline", "none"])
async def test_no_connection_says_scan_again_when_online(api: str) -> None:
    """A ``NetworkError``, or no client at all, is "No connection", nothing queued."""
    client = client_for(httpx.MockTransport(offline)) if api == "offline" else None
    result = await look_up(client, badge(1), categories=BOTH)
    assert result == ScanResult(
        ScanOutcome.DENIED, NO_CONNECTION, "MOCK0001", (NEEDS_CONNECTION,), "MOCK0001"
    )
    if client is not None:
        await client.aclose()


@pytest.mark.parametrize(
    ("status", "content"), [(500, b'{"error": "Boom"}'), (200, b'{"data": []}')]
)
async def test_another_failure_is_couldn_t_check_never_nothing(
    status: int, content: bytes
) -> None:
    """A refusal or an unreadable reply is "Couldn't check this badge" (D-120)."""
    client = client_for(replying(status, content))
    result = await look_up(client, badge(1), categories=BOTH)
    assert (result.outcome, result.word) == (ScanOutcome.DENIED, NOT_CHECKED)
    await client.aclose()


@pytest.mark.parametrize(
    ("names", "said"),
    [
        ([], ""),
        (["T-Shirt"], "T-Shirt"),
        (["T-Shirt", "Swag Bag"], "T-Shirt or Swag Bag"),
        (["A", "B", "C"], "A, B or C"),
    ],
)
def test_spoken_list_joins_names_with_or(names: list[str], said: str) -> None:
    """The categories read as a phrase, the last after "or"."""
    assert spoken_list(names) == said
