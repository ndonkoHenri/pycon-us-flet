"""Tests for the check-in API's payloads: ``core/check_in.py`` and ``check_in_api.py``.

The parsers read every reply the mock sends and leave out bad entries (API-05..API-07);
the door and swag splits of the seeded catalog (DOOR-01, SHIRT-01); the chronological
sort in the conference year (DOOR-02); both redeem bodies byte for byte, signed and
accepted by the mock under both capture semantics (D-57). The fetches run against the
mock's real transport, signed in as the seeded staff account, or a fixed
``httpx.MockTransport`` reply.
"""

import json
from datetime import UTC, datetime

import pytest

from pycon_us import config
from pycon_us.check_in_api import fetch_attendee_products, fetch_catalog, redeem
from pycon_us.core.check_in import (
    AttendeeProducts,
    Catalog,
    Category,
    Item,
    Product,
    RedeemReply,
    door_catalog,
    is_swag,
    parse_attendee_products,
    parse_catalog,
    parse_redeem_reply,
    redeem_payload,
    swag_catalog,
)
from pycon_us.core.door_sessions import product_sort_key, session_parts
from pycon_us.core.signing import canonical_body
from pycon_us.services.api import ApiError
from tests.api_clients import client_for, replying, signed_in
from tests.mock_calls import call, state_at
from tools.mock_api.state import Capture, Redemption

SCANNED_AT = 1_780_000_000.5
"""A scan time, epoch seconds: 2026-05-28T20:26:40.500Z."""


def seeded_catalog() -> Catalog:
    """Return the mock's catalog, read by ``parse_catalog`` from its own reply."""
    status, reply = call(state_at(), "GET", "check_in/redeemable/", "staff")
    assert status == 200
    return parse_catalog(reply)


def test_the_seeded_catalog_reads_whole() -> None:
    """Every seeded category and product is read, in the reply's order."""
    catalog = seeded_catalog()
    assert [c.name for c in catalog.categories] == [
        "Tutorials",
        "Summits",
        "T-Shirt",
        "Swag Bag",
    ]
    assert [p.id for p in catalog.products] == [10, 11, 20, 30, 31, 40]
    assert catalog.products[0] == Product(
        10, "Wed May 13 9:00 AM - All about decorators", 1
    )


@pytest.mark.parametrize(
    "product",
    [
        "Swag Bag",
        {"name": "No id", "category": 1},
        {"id": True, "name": "A bool id", "category": 1},
        {"id": 5.5, "name": "A float id", "category": 1},
        {"id": 5, "category": 1},
        {"id": 5, "name": "  ", "category": 1},
        {"id": 5, "name": "Unknown category", "category": 9},
        {"id": 5, "name": "No category"},
        {"id": 1, "name": "Repeated id", "category": 1},
    ],
)
def test_a_malformed_catalog_entry_is_left_out(product: object) -> None:
    """A product without a usable id, name or known category goes; the good one stays."""
    reply = {
        "redeemable_categories": [{"id": 1, "name": "Tutorials"}, {"id": "x"}],
        "redeemable_products": [{"id": "1", "name": "Talk", "category": "1"}, product],
    }
    assert parse_catalog(reply) == Catalog(
        (Category(1, "Tutorials"),), (Product(1, "Talk", 1),)
    )


@pytest.mark.parametrize(
    "reply",
    [
        None,
        [],
        {},
        {"redeemable_categories": []},
        {"redeemable_categories": [], "redeemable_products": {}},
    ],
)
def test_a_catalog_without_its_two_lists_is_refused(reply: object) -> None:
    """Not both lists: a ``TypeError``, which the fetch makes an ``ApiError``."""
    with pytest.raises(TypeError):
        parse_catalog(reply)


def test_the_door_and_swag_splits_are_disjoint_and_cover_the_catalog() -> None:
    """Tutorials and Summits are the door's, T-Shirt and Swag Bag swag's; none is lost."""
    catalog = seeded_catalog()
    door, swag = door_catalog(catalog), swag_catalog(catalog)
    assert [c.name for c in door.categories] == ["Tutorials", "Summits"]
    assert [c.name for c in swag.categories] == ["T-Shirt", "Swag Bag"]
    assert [p.id for p in door.products] == [10, 11, 20]
    assert [p.id for p in swag.products] == [30, 31, 40]
    assert set(door.products).isdisjoint(swag.products)
    assert set(door.products) | set(swag.products) == set(catalog.products)


@pytest.mark.parametrize(
    ("name", "swag"),
    [("T-Shirt", True), ("SWAG bag", True), ("Tshirts", True), ("Summits", False)],
)
def test_is_swag_is_ionic_s_case_insensitive_pattern(name: str, swag: bool) -> None:
    """``/shirt|swag/i``: anywhere in the name, any case."""
    assert is_swag(name) is swag


def test_sessions_sort_chronologically_and_undated_names_last() -> None:
    """Thu after Wed and 1:30 PM after 9:00 AM; names without a date sort by name after."""
    names = [p.name for p in seeded_catalog().products]
    ordered = sorted(names, key=lambda n: product_sort_key(n, config.YEAR))
    assert ordered == [
        "Wed May 13 9:00 AM - All about decorators",
        "Wed May 13 1:30 PM - Async in depth",
        "Thu May 14 10:00 AM - Example Summit",
        "Swag Bag",
        "T-Shirt (L)",
        "T-Shirt (M)",
    ]


def test_the_sort_uses_the_year_given_and_reads_noon_and_midnight() -> None:
    """The start is in the year passed in, 12 PM is noon, 12 AM midnight, any case."""
    assert product_sort_key("may 13 12:15 am - Early", 2031)[1] == datetime(
        2031, 5, 13, 0, 15, tzinfo=UTC
    )
    assert product_sort_key("Wed May 13 12:15 PM - Lunch", 2031)[1] == datetime(
        2031, 5, 13, 12, 15, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "name", ["Feb 30 9:00 AM - No such day", "May 13 13:00 PM - No such hour", "Talk"]
)
def test_a_name_without_a_valid_date_sorts_last(name: str) -> None:
    """An impossible date counts as none: after every session, not an error."""
    dated = product_sort_key("Dec 31 11:59 PM - Late", config.YEAR)
    assert product_sort_key(name, config.YEAR) > dated


def test_ties_sort_by_folded_name() -> None:
    """Two sessions at one time go by name, case and accents folded."""
    names = [
        "Wed May 13 9:00 AM - b",
        "Wed May 13 9:00 AM - Á",
        "Wed May 13 9:00 AM - a",
    ]
    assert sorted(names, key=lambda n: product_sort_key(n, config.YEAR)) == [
        "Wed May 13 9:00 AM - a",
        "Wed May 13 9:00 AM - Á",
        "Wed May 13 9:00 AM - b",
    ]


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        (
            "Wed May 13 9:00 AM - All about decorators",
            ("All about decorators", "Wed 9:00 AM"),
        ),
        ("May 14 1:30 pm: Async", ("Async", "May 14 1:30 PM")),
        ("Thu May 14 10:00 AM – Summit", ("Summit", "Thu 10:00 AM")),
        ("Thu May 14 10:00 AM", None),
        ("T-Shirt (M)", None),
    ],
)
def test_session_parts_split_the_title_from_the_day_and_time(
    name: str, parts: tuple[str, str] | None
) -> None:
    """The title after the separator, the weekday (or the date) and the time; else None."""
    assert session_parts(name) == parts


def door_lookup(code: str, product_ids: str = "10,11") -> tuple[int, object]:
    """Return the mock's door ``fetch_products`` status and reply for ``code``."""
    query = (
        f"attendee_access_code={code}&product_pk_list={product_ids}"
        "&mode=door_check_mode"
    )
    return call(state_at(), "GET", f"check_in/fetch_products/?{query}", "staff")


def test_a_door_lookup_reads_the_attendee_and_the_door_fields() -> None:
    """Door mode: the attendee, their items by category and the dietary fields."""
    status, reply = door_lookup("MOCK0002")
    assert status == 200
    assert parse_attendee_products(reply) == AttendeeProducts(
        "MOCK0002",
        "Grace Sample",
        2,
        (("Tutorials", (Item(11, "Wed May 13 1:30 PM - Async in depth", 1, 1),)),),
        dietary="",
        has_allergy=True,
        allergy="peanuts",
    )


def test_a_swag_lookup_has_no_door_fields_and_sorts_its_categories() -> None:
    """Swag mode: categories by name, as Ionic's ``keyvalue`` showed them; no dietary."""
    query = "attendee_access_code=MOCK0001&category_pk_list=4,3&mode=redemption_mode"
    status, reply = call(
        state_at(), "GET", f"check_in/fetch_products/?{query}", "staff"
    )
    assert status == 200
    products = parse_attendee_products(reply)
    assert [name for name, _ in products.items_by_category] == ["Swag Bag", "T-Shirt"]
    assert products.items_by_category[1][1] == (Item(30, "T-Shirt (M)", 2, 2),)
    assert (products.dietary, products.has_allergy, products.allergy) == (None,) * 3


def test_a_malformed_item_or_empty_category_is_left_out() -> None:
    """Bad items go, a category left empty goes, odd door fields are None."""
    good = {"product_id": 1, "product_name": "Talk", "redeemable": 0, "purchased": 1}
    reply = {
        "attendee_access_code": "MOCK0001",
        "attendee_id": True,
        "redeemable_products_by_category": {
            "B": [good, {**good, "redeemable": -1}, {**good, "purchased": 1.0}, "x"],
            "A": [{**good, "product_name": ""}],
            "C": {},
        },
        "dietary": 7,
        "has_allergy": "yes",
    }
    assert parse_attendee_products(reply) == AttendeeProducts(
        "MOCK0001", "", None, (("B", (Item(1, "Talk", 0, 1),)),)
    )


@pytest.mark.parametrize(
    "reply",
    [
        None,
        {"redeemable_products_by_category": {}},
        {"attendee_access_code": 1, "redeemable_products_by_category": {}},
        {"attendee_access_code": "MOCK0001", "redeemable_products_by_category": []},
    ],
)
def test_a_lookup_without_code_or_items_is_refused(reply: object) -> None:
    """No access code or no items object: a ``TypeError``."""
    with pytest.raises(TypeError):
        parse_attendee_products(reply)


DOOR_BODY = (
    b'{"attendee_access_code":"MOCK0003","badge_validator":"v4l1d03",'
    b'"scanned_at":"2026-05-28T20:26:40.500Z",'
    b'"product-redeem-10":10,"product-10-quantity":2,'
    b'"product-redeem-20":20,"product-20-quantity":1}'
)
"""The door's body: ids as numbers (``door-check.page.ts`` 177-188)."""

SWAG_BODY = (
    b'{"attendee_access_code":"MOCK0001","badge_validator":"",'
    b'"scanned_at":"2026-05-28T20:26:40.500Z",'
    b'"product-redeem-30":"30","product-30-quantity":2,'
    b'"product-redeem-40":"40","product-40-quantity":1}'
)
"""Swag's body: ids as strings, ``""`` for a missing validator (153-165)."""


def test_the_door_body_is_ionic_s_byte_for_byte() -> None:
    """The fixed keys, then a pair per product in order; ids as numbers."""
    payload = redeem_payload(
        "MOCK0003", "v4l1d03", SCANNED_AT, {10: 2, 20: 1}, swag=False
    )
    assert canonical_body(payload) == DOOR_BODY


def test_the_swag_body_is_ionic_s_byte_for_byte() -> None:
    """Ids as strings and a missing validator sent as ``""``."""
    payload = redeem_payload("MOCK0001", None, SCANNED_AT, {30: 2, 40: 1}, swag=True)
    assert canonical_body(payload) == SWAG_BODY


def test_the_door_leaves_out_a_missing_validator_and_keeps_an_empty_one() -> None:
    """None (a badge without ``:``) is omitted, as ``JSON.stringify`` drops undefined."""
    missing = redeem_payload("MOCK0003", None, SCANNED_AT, {10: 1}, swag=False)
    empty = redeem_payload("MOCK0003", "", SCANNED_AT, {10: 1}, swag=False)
    assert list(missing)[:2] == ["attendee_access_code", "scanned_at"]
    assert empty["badge_validator"] == ""


@pytest.mark.parametrize("quantity", [0, -1, True, 1.0])
def test_a_quantity_that_is_not_positive_is_refused(quantity: object) -> None:
    """The server refuses it, so building one is a ``ValueError``."""
    with pytest.raises(ValueError, match="quantity"):
        redeem_payload("MOCK0001", "", SCANNED_AT, {30: quantity}, swag=True)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("capture", ["idempotent", "non_idempotent"])
@pytest.mark.parametrize(
    ("body", "redeemed"),
    [(DOOR_BODY, (10, 20)), (SWAG_BODY, (30, 40))],
)
def test_both_bodies_are_accepted_by_the_mock(
    capture: Capture, body: bytes, redeemed: tuple[int, ...]
) -> None:
    """Signed and sent as built, each body redeems its products under both semantics."""
    state = state_at(capture)
    payload = json.loads(body)
    status, reply = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert status == 200
    assert parse_redeem_reply(reply) == RedeemReply((), redeemed)
    assert len(state.redemptions) == len(redeemed)


def test_a_redeem_reply_with_errors_keeps_the_messages() -> None:
    """A product already redeemed is an error; the one beside it still goes through."""
    state = state_at()
    state.redemptions.append(Redemption("MOCK0001", 30, 2, "earlier"))
    payload = redeem_payload("MOCK0001", "", SCANNED_AT, {30: 1, 40: 1}, swag=True)
    status, reply = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert status == 200
    assert parse_redeem_reply(reply) == RedeemReply(
        ("T-Shirt (M) was already redeemed.",), (40,)
    )


def test_a_malformed_redeem_entry_is_left_out() -> None:
    """Errors without a message and items without an id go; the rest stay in order."""
    reply = {
        "errors": [{"message": "One"}, {"message": ""}, {}, "Two"],
        "redeemable_products_by_category": {
            "T-Shirt": [{"product_id": 30}, {"product_id": "x"}, 7],
            "Bag": [{"product_id": "40"}],
            "Odd": {},
        },
    }
    assert parse_redeem_reply(reply) == RedeemReply(("One",), (30, 40))


@pytest.mark.parametrize(
    "reply",
    [None, {"errors": []}, {"errors": {}, "redeemable_products_by_category": {}}],
)
def test_a_redeem_reply_without_its_two_members_is_refused(reply: object) -> None:
    """Not ``errors`` and the redeemed object: a ``TypeError``."""
    with pytest.raises(TypeError):
        parse_redeem_reply(reply)


async def test_the_fetches_and_redeem_read_the_mock_signed_in_as_staff() -> None:
    """The catalog, a swag lookup and a swag redeem, over the signed client."""
    client, recorder, state = await signed_in("staff")
    catalog = await fetch_catalog(client)
    swag = swag_catalog(catalog)
    products = await fetch_attendee_products(
        client, "MOCK0001", [c.id for c in swag.categories], door=False
    )
    assert recorder.sent[-1].url.query == (
        b"attendee_access_code=MOCK0001&category_pk_list=3,4&mode=redemption_mode"
    )
    quantities = {
        item.product_id: item.redeemable
        for _, items in products.items_by_category
        for item in items
    }
    payload = redeem_payload("MOCK0001", None, SCANNED_AT, quantities, swag=True)
    assert await redeem(client, payload) == RedeemReply((), (40, 30))
    assert recorder.sent[-1].content == canonical_body(payload)
    assert len(state.redemptions) == 2
    await client.aclose()


async def test_a_door_lookup_of_an_unknown_attendee_is_a_404() -> None:
    """The mock answers 404 for a code it doesn't know: an ``ApiError``."""
    client, _, _ = await signed_in("staff")
    with pytest.raises(ApiError) as caught:
        await fetch_attendee_products(client, "NOBODY", [10], door=True)
    assert caught.value.status == 404
    await client.aclose()


@pytest.mark.parametrize("fetch", ["catalog", "lookup", "redeem"])
async def test_an_unreadable_reply_is_an_api_error(fetch: str) -> None:
    """A 200 that isn't the documented object is an ``ApiError`` (D-120)."""
    client = client_for(replying(200, b'{"data": []}'))
    with pytest.raises(ApiError):
        if fetch == "catalog":
            await fetch_catalog(client)
        elif fetch == "lookup":
            await fetch_attendee_products(client, "MOCK0001", [10], door=True)
        else:
            await redeem(client, {})
    await client.aclose()
