"""Tests for Swag pickup's hand-out, ``swag.hand_out()`` and the offer (#769; SHIRT-04).

Each row of the issue's outcome table against the mock's real transport, signed in as
the seeded staff account (Ada: 2 T-shirts, product 30, and a bag, 40), or a fixed
``httpx.MockTransport`` reply: all, part or nothing handed out, no connection, an
answer lost or unreadable after the server applied it (D-410), a refusal. Nothing is
ever resent or queued (D-56, D-57).
"""

import json

import httpx
import pytest

from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.services.api import ApiClient
from pycon_us.services.endpoints import REDEEM
from pycon_us.swag import (
    ALREADY,
    MAY_BE_PICKED_UP,
    NOT_CONFIRMED,
    NOT_HANDED_OUT,
    NOTHING_HANDED_OUT,
    NOTHING_RECORDED,
    PARTLY,
    READY,
    RESCAN,
    Offer,
    hand_out,
    look_up,
)
from tests.api_clients import Recorder, ReplyReplaced, client_for, replying, signed_in
from tests.test_swag import BOTH, badge
from tools.mock_api.state import MockState, Redemption

ADA = badge(1)
SCANNED_AT = 1778860800.25
"""When the badge was scanned: 2026-05-15T16:00:00.250Z."""


async def offer_for(client: ApiClient, scanned: Badge = ADA) -> Offer:
    """Return the offer a lookup of ``scanned`` makes, as the sheet gets it."""
    offers: list[Offer] = []

    async def keep(given: Offer) -> ScanResult | None:
        """Keep the offer and cancel, as Cancel would."""
        offers.append(given)
        return None

    await look_up(
        client, scanned, categories=BOTH, offer=keep, clock=lambda: SCANNED_AT
    )
    (given,) = offers
    return given


def redeemed(state: MockState) -> list[tuple[int, int]]:
    """The products and quantities the mock recorded for Ada."""
    return [
        (r.product_id, r.quantity)
        for r in state.redemptions
        if r.access_code == "MOCK0001"
    ]


async def test_everything_handed_out_says_the_count_and_a_rescan_says_picked_up() -> (
    None
):
    """3 items: "Handed out 3 items", the name; recorded once; next scan "Already"."""
    client, recorder, state = await signed_in("staff")
    offer = await offer_for(client)
    assert offer.available == {40: 1, 30: 2}  # the bag's category sorts first
    result = await hand_out(client, offer, offer.available)
    assert result == ScanResult(
        ScanOutcome.ACCEPTED, "Handed out 3 items", "Ada Example", (), "MOCK0001"
    )
    assert sorted(redeemed(state)) == [(30, 2), (40, 1)]
    body = json.loads(recorder.sent[-1].content)
    assert body == {
        "attendee_access_code": "MOCK0001",
        "badge_validator": "v4l1d01",
        "scanned_at": "2026-05-15T16:00:00.250Z",  # the scan's time
        "product-redeem-40": "40",
        "product-40-quantity": 1,
        "product-redeem-30": "30",
        "product-30-quantity": 2,
    }
    again = await look_up(client, ADA, categories=BOTH)
    assert (again.outcome, again.word) == (ScanOutcome.DUPLICATE, ALREADY)
    await client.aclose()


async def test_one_item_says_item_and_the_rest_stays_available() -> None:
    """The bag alone: "Handed out 1 item"; the T-shirts are still left after."""
    client, _, state = await signed_in("staff")
    offer = await offer_for(client)
    result = await hand_out(client, offer, {40: 1})
    assert result.word == "Handed out 1 item"
    assert redeemed(state) == [(40, 1)]
    assert (await offer_for(client)).available == {30: 2}
    await client.aclose()


async def test_part_handed_out_is_a_duplicate_with_the_server_s_messages() -> None:
    """The bag taken meanwhile: "Partly handed out", the name and the mock's message."""
    client, _, state = await signed_in("staff")
    offer = await offer_for(client)
    state.redemptions.append(Redemption("MOCK0001", 40, 1, "elsewhere"))
    result = await hand_out(client, offer, offer.available)
    assert (result.outcome, result.word, result.title) == (
        ScanOutcome.DUPLICATE,
        PARTLY,
        "Ada Example",
    )
    assert len(result.details) == 1 and "already redeemed" in result.details[0]
    assert sorted(redeemed(state)) == [(30, 2), (40, 1)]
    await client.aclose()


async def test_nothing_handed_out_says_the_messages() -> None:
    """Everything taken meanwhile: "Nothing handed out" and each message."""
    client, _, state = await signed_in("staff")
    offer = await offer_for(client)
    state.redemptions += [
        Redemption("MOCK0001", 40, 1, "elsewhere"),
        Redemption("MOCK0001", 30, 2, "elsewhere"),
    ]
    result = await hand_out(client, offer, offer.available)
    assert (result.outcome, result.word) == (ScanOutcome.DENIED, NOTHING_HANDED_OUT)
    assert len(result.details) == 2
    await client.aclose()


async def test_nothing_redeemed_without_a_message_says_items_may_be_picked_up() -> None:
    """A reply with no errors and nothing redeemed still says why it may be."""
    staff, _, _ = await signed_in("staff")
    offer = await offer_for(staff)
    await staff.aclose()
    client = client_for(
        replying(200, b'{"errors": [], "redeemable_products_by_category": {}}')
    )
    result = await hand_out(client, offer, offer.available)
    assert (result.outcome, result.word, result.details) == (
        ScanOutcome.DENIED,
        NOTHING_HANDED_OUT,
        (MAY_BE_PICKED_UP,),
    )
    await client.aclose()


async def test_no_connection_says_nothing_was_recorded() -> None:
    """A connect error (never sent): "Not handed out", "No connection. …"; none kept."""
    client, _, state = await signed_in("staff")
    offer = await offer_for(client)
    state.faults.inject("connect")
    result = await hand_out(client, offer, offer.available)
    assert result == ScanResult(
        ScanOutcome.DENIED,
        NOT_HANDED_OUT,
        "Ada Example",
        (NOTHING_RECORDED,),
        "MOCK0001",
    )
    assert redeemed(state) == []
    assert (await hand_out(None, offer, offer.available)).details == (NOTHING_RECORDED,)
    await client.aclose()


async def test_a_lost_answer_is_not_confirmed_and_a_rescan_shows_the_truth() -> None:
    """The mock applied it and the reply was lost: "Not confirmed", rescan; never resent."""
    client, recorder, state = await signed_in("staff")
    offer = await offer_for(client)
    state.faults.inject("lost_response")
    result = await hand_out(client, offer, offer.available)
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_CONFIRMED, "Ada Example", (RESCAN,), "MOCK0001"
    )
    assert sorted(redeemed(state)) == [(30, 2), (40, 1)]  # applied once
    assert len(redeems(recorder)) == 1  # never resent
    again = await look_up(client, ADA, categories=BOTH)
    assert again.word == ALREADY  # the rescan shows what was really recorded
    await client.aclose()


@pytest.mark.parametrize("body", [b"<html>ok</html>", b"\xff\xfe", b'{"ok": true}'])
async def test_an_unreadable_answer_is_not_confirmed_and_never_resent(
    body: bytes,
) -> None:
    """The mock applied it and the reply can't be read: "Not confirmed", rescan (#874)."""
    client, recorder, state = await signed_in("staff")
    offer = await offer_for(client)
    applying = recorder.inner
    recorder.inner = ReplyReplaced(applying, body)
    result = await hand_out(client, offer, offer.available)
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_CONFIRMED, "Ada Example", (RESCAN,), "MOCK0001"
    )
    assert sorted(redeemed(state)) == [(30, 2), (40, 1)]  # applied once
    assert len(redeems(recorder)) == 1  # never resent
    recorder.inner = applying
    again = await look_up(client, ADA, categories=BOTH)
    assert again.word == ALREADY  # the rescan shows what was really recorded
    await client.aclose()


async def test_an_error_envelope_under_200_stays_a_refusal() -> None:
    """A ``{"code", "error"}`` reply is the server's no: "Not handed out", its words."""
    client, recorder, state = await signed_in("staff")
    offer = await offer_for(client)
    recorder.inner = replying(200, b'{"code": 500, "error": "Boom."}')
    result = await hand_out(client, offer, offer.available)
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_HANDED_OUT, "Ada Example", ("Boom.",), "MOCK0001"
    )
    assert redeemed(state) == []
    await client.aclose()


async def test_a_refusal_is_not_handed_out_with_the_server_s_message() -> None:
    """A wrong validator (404): "Not handed out" and the mock's own message."""
    client, _, state = await signed_in("staff")
    offer = await offer_for(client, Badge("MOCK0001", "wrong", "wrong"))
    result = await hand_out(client, offer, offer.available)
    assert (result.outcome, result.word) == (ScanOutcome.DENIED, NOT_HANDED_OUT)
    assert len(result.details) == 1 and result.details[0]
    assert redeemed(state) == []
    await client.aclose()


async def test_the_offer_s_answer_replaces_the_lookup_s_and_cancel_keeps_it() -> None:
    """Handed out: its result; cancelled (None): "Ready to hand out" stays."""
    client, _, _ = await signed_in("staff")
    done = ScanResult(ScanOutcome.ACCEPTED, "Handed out 3 items", "Ada Example")

    async def handed(_: Offer) -> ScanResult | None:
        """Hand everything out, as a tap on Hand out would end."""
        return done

    assert await look_up(client, ADA, categories=BOTH, offer=handed) == done
    cancelled = await look_up(client, ADA, categories=BOTH, offer=lambda _: _none())
    assert cancelled.word == READY
    await client.aclose()


async def test_no_offer_without_items_left() -> None:
    """Nothing bought, or an unknown badge: the sheet is never offered."""
    client, _, _ = await signed_in("staff")

    async def never(_: Offer) -> ScanResult | None:
        """Fail: nothing should be offered."""
        raise AssertionError("offered")

    for scanned in (badge(4), Badge("NOBODY", "x", "x")):
        result = await look_up(client, scanned, categories=BOTH, offer=never)
        assert result.outcome is ScanOutcome.DENIED
    await client.aclose()


async def _none() -> ScanResult | None:
    """Return None, as a cancelled sheet does."""
    return None


def redeems(recorder: Recorder) -> list[httpx.Request]:
    """The ``redeem`` POSTs the client sent."""
    return [r for r in recorder.sent if r.url.path.endswith(REDEEM.path)]
