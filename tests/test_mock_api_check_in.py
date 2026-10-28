"""The mock API's check-in endpoints: door check and swag pickup (API-05..API-07).

``check_in/redeemable``, ``attendees_by_product_with_quantity``, ``fetch_products`` and
``redeem_products`` as ``tools/mock_api/README.md`` describes them, under both capture
semantics (D-57). The role gates of every staff endpoint are pinned here too.
"""

import re

import httpx
import pytest

from pycon_us.core.signing import auth_headers
from tests.mock_calls import BASE, NOW, account, call, state_at
from tools.mock_api.state import MockState, Redemption
from tools.mock_api.transport import mock_transport

SWAG = re.compile("shirt|swag", re.IGNORECASE)
"""How Ionic tells swag categories from door ones."""

FETCH_QUERY = (
    "attendee_access_code=MOCK0001",
    "category_pk_list=3",
    "mode=redemption_mode",
)
"""A swag ``fetch_products`` query's parameters, in Ionic's order."""

STAFF_ENDPOINTS = [
    ("GET", "check_in/redeemable/", "door_check_in"),
    ("GET", "check_in/attendees_by_product_with_quantity/10/", "door_check_in"),
    (
        "GET",
        f"check_in/fetch_products/?{'&'.join(FETCH_QUERY)}",
        "door_check_in",
    ),
    ("POST", "check_in/redeem_products/", "door_check_in"),
    ("GET", "mask_violations/attendees/", "mask_violation"),
    ("GET", "mask_violations/capture/?attendee_access_code=MOCK0001", "mask_violation"),
    ("POST", "mask_violations/capture/", "mask_violation"),
    ("GET", "lead_retrieval/sponsors/", "lead"),
    (
        "GET",
        "lead_retrieval/capture/?attendee_access_code=MOCK0001&badge_validator=v4l1d01",
        "lead",
    ),
    ("POST", "lead_retrieval/MOCK0001/note/", "lead"),
]
"""Every staff endpoint, with the flag it needs (``lead``: lead retrieval or door)."""

DOOR_ROLES = {"door_check_in": "staff", "mask_violation": "coc", "lead": "sponsor"}
"""A seeded role that holds each gate's flag."""


def door_payload(code: str, scanned_at: str, **quantities: int) -> dict[str, object]:
    """A door-check payload as Ionic builds it: no validator, ids as numbers."""
    payload: dict[str, object] = {
        "attendee_access_code": code,
        "scanned_at": scanned_at,
    }
    for pid, qty in quantities.items():
        payload |= {f"product-redeem-{pid[1:]}": int(pid[1:])}
        payload |= {f"product-{pid[1:]}-quantity": qty}
    return payload


def swag_payload(code: str, validator: str, **quantities: int) -> dict[str, object]:
    """A swag payload as Ionic builds it: a validator (maybe ``""``), ids as strings."""
    payload: dict[str, object] = {
        "attendee_access_code": code,
        "badge_validator": validator,
        "scanned_at": "2026-05-15T09:00:00.000Z",
    }
    for pid, qty in quantities.items():
        payload |= {f"product-redeem-{pid[1:]}": pid[1:]}
        payload |= {f"product-{pid[1:]}-quantity": qty}
    return payload


def fetch(state: MockState, query: str, role: str = "staff") -> tuple[int, object]:
    """``fetch_products`` with the query exactly as Ionic interpolates it."""
    return call(state, "GET", f"check_in/fetch_products/?{query}", role)


def test_the_seed_has_door_and_swag_products_and_badged_attendees() -> None:
    """Both category kinds have products, and every attendee has a fake badge."""
    state = state_at()
    kinds = {bool(SWAG.search(c.name)) for c in state.categories}
    assert kinds == {True, False}
    assert {p.category for p in state.products.values()} == {
        c.id for c in state.categories
    }
    for each in state.attendees.values():
        assert each.email.endswith("@example.com")
        assert each.access_code.startswith("MOCK") and each.validator
    assert any(a.violations for a in state.attendees.values())
    assert any(s.name.startswith('"') for s in state.sponsors)


@pytest.mark.parametrize(("method", "endpoint", "gate"), STAFF_ENDPOINTS)
def test_every_staff_endpoint_is_signed_and_role_gated(
    method: str, endpoint: str, gate: str
) -> None:
    """No key is 401; a role without the flag is 403 ``{code, error}``; with it, not."""
    state = state_at()
    assert call(state, method, endpoint)[0] == 401
    assert call(state, method, endpoint, "attendee") == (
        403,
        {"code": 403, "error": "This account's role can't use this endpoint."},
    )
    outsider = "staff" if gate == "mask_violation" else "coc"
    assert call(state, method, endpoint, outsider)[0] == 403
    assert call(state, method, endpoint, DOOR_ROLES[gate])[0] != 403
    assert call(state, method, endpoint, "all")[0] != 403


def test_the_never_called_attendees_by_product_is_not_served() -> None:
    """Ionic's unused ``attendees_by_product/<id>/`` is a 404 (API-05)."""
    state = state_at()
    assert call(state, "GET", "check_in/attendees_by_product/10/", "staff")[0] == 404


def test_redeemable_lists_every_category_and_product_bare() -> None:
    """The reply is bare ``{redeemable_categories, redeemable_products}``."""
    state = state_at()
    status, body = call(state, "GET", "check_in/redeemable/", "staff")
    assert status == 200
    assert isinstance(body, dict)
    assert {"id": 3, "name": "T-Shirt"} in body["redeemable_categories"]
    assert {
        "id": 10,
        "name": "Wed May 13 9:00 AM - All about decorators",
        "category": 1,
    } in body["redeemable_products"]
    assert len(body["redeemable_products"]) == len(state.products)


def test_inventory_lists_who_bought_a_product_with_their_dietary_needs() -> None:
    """A bare list of buyers: access code as ``id``, quantity bought, dietary fields."""
    state = state_at()
    endpoint = "check_in/attendees_by_product_with_quantity/10/"
    assert call(state, "GET", endpoint, "staff") == (
        200,
        [
            {
                "id": "MOCK0001",
                "quantity": 1,
                "name": "Ada Example",
                "dietary": "vegetarian",
                "has_allergy": False,
                "allergy": "",
            },
            {
                "id": "MOCK0003",
                "quantity": 2,
                "name": "Linus Placeholder",
                "dietary": "vegan",
                "has_allergy": True,
                "allergy": "",
            },
        ],
    )


@pytest.mark.parametrize("product", ["99", "x", "10,11", "1" * 20])
def test_inventory_of_an_unknown_product_is_404(product: str) -> None:
    """An unknown or malformed product id is 404."""
    endpoint = f"check_in/attendees_by_product_with_quantity/{product}/"
    assert call(state_at(), "GET", endpoint, "staff")[0] == 404


def test_fetch_products_for_swag_reads_the_unencoded_category_list() -> None:
    """Swag mode groups what the attendee bought in those categories, no dietary."""
    query = "attendee_access_code=MOCK0001&category_pk_list=3,4&mode=redemption_mode"
    assert fetch(state_at(), query) == (
        200,
        {
            "attendee_access_code": "MOCK0001",
            "attendee_name": "Ada Example",
            "attendee_id": 1,
            "has_items_to_redeem": True,
            "redeemable_products_by_category": {
                "T-Shirt": [
                    {
                        "product_id": 30,
                        "product_name": "T-Shirt (M)",
                        "redeemable": 2,
                        "purchased": 2,
                    }
                ],
                "Swag Bag": [
                    {
                        "product_id": 40,
                        "product_name": "Swag Bag",
                        "redeemable": 1,
                        "purchased": 1,
                    }
                ],
            },
        },
    )


def test_fetch_products_for_the_door_adds_dietary_and_skips_unbought() -> None:
    """Door mode lists only the products named that the attendee bought, plus diet."""
    query = "attendee_access_code=MOCK0002&product_pk_list=10,11&mode=door_check_mode"
    status, body = fetch(state_at(), query)
    assert status == 200
    assert isinstance(body, dict)
    assert body["redeemable_products_by_category"] == {
        "Tutorials": [
            {
                "product_id": 11,
                "product_name": "Wed May 13 1:30 PM - Async in depth",
                "redeemable": 1,
                "purchased": 1,
            }
        ]
    }
    assert (body["dietary"], body["has_allergy"], body["allergy"]) == (
        "",
        True,
        "peanuts",
    )


def test_fetch_products_with_nothing_bought_has_no_items_to_redeem() -> None:
    """An attendee who bought none of the products gets an empty grouping."""
    query = "attendee_access_code=MOCK0004&category_pk_list=3,4&mode=redemption_mode"
    status, body = fetch(state_at(), query)
    assert status == 200
    assert isinstance(body, dict)
    assert body["has_items_to_redeem"] is False
    assert body["redeemable_products_by_category"] == {}


@pytest.mark.parametrize(
    ("query", "status"),
    [
        ("attendee_access_code=NOPE&category_pk_list=3&mode=redemption_mode", 404),
        ("category_pk_list=3&mode=redemption_mode", 400),
        ("attendee_access_code=MOCK0001&category_pk_list=3&mode=other", 400),
        ("attendee_access_code=MOCK0001&mode=redemption_mode", 400),
        (
            "attendee_access_code=MOCK0001&category_pk_list=3,x&mode=redemption_mode",
            400,
        ),
        ("attendee_access_code=MOCK0001&category_pk_list=9&mode=redemption_mode", 404),
        ("attendee_access_code=MOCK0001&product_pk_list=99&mode=door_check_mode", 404),
        (
            "attendee_access_code=MOCK%30001&category_pk_list=3&mode=redemption_mode",
            404,
        ),
    ],
)
def test_fetch_products_refuses_a_bad_query(query: str, status: int) -> None:
    """Missing or bad parameters are 400, unknown ones 404; nothing is decoded."""
    reply_status, body = fetch(state_at(), query)
    assert reply_status == status
    assert isinstance(body, dict) and body.keys() == {"code", "error"}


def test_a_door_redemption_redeems_once_then_reports_already_redeemed() -> None:
    """The door's payload (no validator, numeric ids) redeems; a later scan errs."""
    state = state_at()
    first = door_payload("MOCK0001", "2026-05-13T13:00:00.000Z", p10=1)
    assert call(state, "POST", "check_in/redeem_products/", "staff", first) == (
        200,
        {
            "errors": [],
            "redeemable_products_by_category": {
                "Tutorials": [
                    {
                        "product_id": 10,
                        "product_name": "Wed May 13 9:00 AM - All about decorators",
                        "redeemable": 0,
                        "purchased": 1,
                    }
                ]
            },
        },
    )
    later = door_payload("MOCK0001", "2026-05-13T13:05:00.000Z", p10=1)
    assert call(state, "POST", "check_in/redeem_products/", "staff", later) == (
        200,
        {
            "errors": [
                {
                    "message": "Wed May 13 9:00 AM - All about decorators was already redeemed."
                }
            ],
            "redeemable_products_by_category": {},
        },
    )
    assert len(state.redemptions) == 1


def test_a_swag_redemption_takes_string_ids_and_an_empty_validator() -> None:
    """Swag sends ids as strings and ``""`` for a missing validator; both work."""
    state = state_at()
    payload = swag_payload("MOCK0001", "", p30=2, p40=1)
    status, body = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert status == 200
    assert isinstance(body, dict)
    assert body["errors"] == []
    assert set(body["redeemable_products_by_category"]) == {"T-Shirt", "Swag Bag"}
    assert [(r.product_id, r.quantity) for r in state.redemptions] == [(30, 2), (40, 1)]
    query = "attendee_access_code=MOCK0001&category_pk_list=3,4&mode=redemption_mode"
    fetched = fetch(state, query)[1]
    assert isinstance(fetched, dict)
    assert fetched["has_items_to_redeem"] is False


def test_a_partial_redemption_redeems_what_it_can_and_lists_the_rest() -> None:
    """One redeemable product goes through; the unbought and the too-many err."""
    state = state_at()
    payload = swag_payload("MOCK0002", "v4l1d02", p31=1, p30=1)
    payload |= {"product-redeem-11": 11, "product-11-quantity": 5}
    status, body = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert status == 200
    assert isinstance(body, dict)
    assert body["errors"] == [
        {"message": "T-Shirt (M) was not purchased."},
        {"message": "Wed May 13 1:30 PM - Async in depth: only 1 left to redeem."},
    ]
    assert list(body["redeemable_products_by_category"]) == ["T-Shirt"]


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"badge_validator": "wrong"}, 404),
        ({"attendee_access_code": "NOPE"}, 404),
        ({"attendee_access_code": 1}, 404),
        ({"badge_validator": None}, 400),
        ({"scanned_at": None}, 400),
        ({"product-redeem-99": 99, "product-99-quantity": 1}, 404),
        ({"product-redeem-30": 31}, 400),
        ({"product-redeem-30": True}, 400),
        ({"product-30-quantity": 0}, 400),
        ({"product-30-quantity": "1"}, 400),
        ({"product-30-quantity": 1.5}, 400),
    ],
)
def test_a_bad_redeem_payload_is_refused_and_redeems_nothing(
    change: dict[str, object], status: int
) -> None:
    """A wrong badge, unknown product or malformed pair redeems nothing."""
    state = state_at()
    payload = swag_payload("MOCK0001", "v4l1d01", p30=1) | change
    reply_status, body = call(
        state, "POST", "check_in/redeem_products/", "staff", payload
    )
    assert reply_status == status
    assert isinstance(body, dict) and body.keys() == {"code", "error"}
    assert state.redemptions == []


def test_a_repeated_redemption_is_applied_once_when_idempotent() -> None:
    """The same payload twice is recorded once and answered the same (D-57)."""
    state = state_at("idempotent")
    payload = door_payload("MOCK0001", "2026-05-15T09:00:00.000Z", p30=1)
    first = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    again = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert first == again
    assert state.redemptions == [
        Redemption("MOCK0001", 30, 1, "2026-05-15T09:00:00.000Z")
    ]


def test_a_repeated_redemption_is_applied_twice_when_not_idempotent() -> None:
    """Under non-idempotent capture each request redeems while quantity is left."""
    state = state_at("non_idempotent")
    payload = door_payload("MOCK0001", "2026-05-15T09:00:00.000Z", p30=1)
    for _ in range(3):
        call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert len(state.redemptions) == 2  # Ada bought two; the third request errs
    status, body = call(state, "POST", "check_in/redeem_products/", "staff", payload)
    assert status == 200
    assert body == {
        "errors": [{"message": "T-Shirt (M) was already redeemed."}],
        "redeemable_products_by_category": {},
    }


def test_an_unknown_capture_semantics_is_refused() -> None:
    """``MockState`` only models the two semantics D-57 names."""
    with pytest.raises(ValueError, match="capture"):
        MockState(2026, [], capture="sometimes")  # type: ignore[arg-type]


async def test_the_unencoded_fetch_query_survives_httpx_and_the_transport() -> None:
    """Ionic's raw ``a,b`` list goes through httpx unchanged and signs as sent."""
    state = state_at()
    staff = account(state, "staff")
    path = (
        f"{BASE}check_in/fetch_products/?attendee_access_code=MOCK0001"
        "&category_pk_list=3,4&mode=redemption_mode"
    )
    headers = auth_headers(staff.key, staff.secret, NOW, "GET", path, b"")
    async with httpx.AsyncClient(
        transport=mock_transport(state), base_url="http://mock.test"
    ) as client:
        reply = await client.get(
            path, headers={name: str(value) for name, value in headers.items()}
        )
    assert reply.status_code == 200
    assert reply.json()["has_items_to_redeem"] is True
