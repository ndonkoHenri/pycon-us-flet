"""Tests for the door's attendee list: ``core/admission.py`` and ``door_inventory.py``.

``merge()`` sums quantities per code and product, keeps an attendee's details sticky
and leaves out malformed rows (DOOR-03, API-05). ``load_inventory()`` runs one
``INVENTORY`` call per product against the mock's own transport, signed with the
seeded staff account's key, and reports each one that finishes; a 404 or a timeout
fails that product alone (D-120).
"""

import httpx
import pytest

from pycon_us.core.admission import Attendee, Inventory, attendee_count, merge
from pycon_us.door_inventory import Loaded, load_inventory
from pycon_us.services.api import ApiClient
from tests.api_clients import Login, client_for
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tools.mock_api.transport import mock_transport

ADA = {
    "id": "MOCK0001",
    "quantity": 1,
    "name": "Ada Example",
    "dietary": "vegetarian",
    "has_allergy": False,
    "allergy": "",
}
LINUS = {
    "id": "MOCK0003",
    "quantity": 2,
    "name": "Linus Placeholder",
    "dietary": "vegan",
    "has_allergy": True,
    "allergy": "",
}
GRACE = {
    "id": "MOCK0002",
    "quantity": 1,
    "name": "Grace Sample",
    "dietary": "",
    "has_allergy": True,
    "allergy": "peanuts",
}


# ------------------------------------------------------------------ merge()


def test_a_reply_is_merged_by_code_with_its_details() -> None:
    """Each row's quantity goes under its code and product; its details are kept."""
    inventory = merge(Inventory(), 10, [ADA, LINUS])
    assert inventory.quantities == {"MOCK0001": {10: 1}, "MOCK0003": {10: 2}}
    assert inventory.attendees["MOCK0001"] == Attendee(
        "MOCK0001", "Ada Example", "vegetarian", False, ""
    )
    assert inventory.attendees["MOCK0003"].has_allergy
    assert attendee_count(inventory) == 2


def test_a_repeated_code_sums_per_product() -> None:
    """The same code again, in one reply or another product's, adds up per product."""
    inventory = merge(Inventory(), 10, [ADA, {"id": "MOCK0001", "quantity": 2}])
    inventory = merge(inventory, 11, [{"id": "MOCK0001", "quantity": 1}])
    inventory = merge(inventory, 11, [{"id": "MOCK0001", "quantity": 1}])
    assert inventory.quantities == {"MOCK0001": {10: 3, 11: 2}}
    assert attendee_count(inventory) == 1


def test_details_are_sticky() -> None:
    """A later row without details, or with empty ones, keeps the earlier ones."""
    inventory = merge(Inventory(), 11, [GRACE])
    later = {"id": "MOCK0002", "quantity": 1, "name": "", "dietary": None}
    inventory = merge(inventory, 12, [later, {"id": "MOCK0002", "quantity": 1}])
    assert inventory.attendees["MOCK0002"] == Attendee(
        "MOCK0002", "Grace Sample", "", True, "peanuts"
    )
    added = merge(
        inventory, 13, [{"id": "MOCK0002", "quantity": 1, "dietary": "kosher"}]
    )
    assert added.attendees["MOCK0002"].dietary == "kosher"
    assert added.attendees["MOCK0002"].name == "Grace Sample"


def test_merge_leaves_the_inventory_it_was_given_alone() -> None:
    """A merge returns a new list: the one before it is unchanged."""
    before = merge(Inventory(), 10, [ADA])
    merge(before, 10, [ADA, GRACE])
    assert before.quantities == {"MOCK0001": {10: 1}}
    assert set(before.attendees) == {"MOCK0001"}


@pytest.mark.parametrize(
    "row",
    [
        "MOCK0009",
        None,
        {"quantity": 1},
        {"id": "", "quantity": 1},
        {"id": "  ", "quantity": 1},
        {"id": 9, "quantity": 1},
        {"id": "MOCK0009"},
        {"id": "MOCK0009", "quantity": 0},
        {"id": "MOCK0009", "quantity": -1},
        {"id": "MOCK0009", "quantity": 1.5},
        {"id": "MOCK0009", "quantity": "1"},
        {"id": "MOCK0009", "quantity": True},
    ],
)
def test_a_malformed_row_is_left_out(row: object) -> None:
    """A row without a code or a positive integer quantity goes; the others stay."""
    inventory = merge(Inventory(), 10, [row, ADA])
    assert inventory.quantities == {"MOCK0001": {10: 1}}
    assert "MOCK0009" not in inventory.attendees


@pytest.mark.parametrize("reply", [None, {}, {"id": "MOCK0001"}, "[]"])
def test_a_reply_that_is_not_a_list_is_refused(reply: object) -> None:
    """Not the documented list: a ``TypeError``, which fails the product."""
    with pytest.raises(TypeError):
        merge(Inventory(), 10, reply)


# ------------------------------------------------------------------ load_inventory()


class Faulty(httpx.AsyncBaseTransport):
    """The mock's transport, but product 12's call times out."""

    def __init__(self) -> None:
        """Answer through a freshly seeded mock."""
        self.inner = mock_transport(state_at())

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Raise ``ReadTimeout`` for product 12, else let the mock answer."""
        if request.url.path.endswith("/12/"):
            raise httpx.ReadTimeout("timed out", request=request)
        return await self.inner.handle_async_request(request)


def staff_client(transport: httpx.AsyncBaseTransport) -> ApiClient:
    """A client over ``transport`` signed with the seeded staff account's key."""
    who = seeded(state_at(), "staff")
    return client_for(transport, Login(who.key, who.secret))


async def test_tutorials_load_whole_with_progress_in_order() -> None:
    """Both of Tutorials' products answer: three attendees, nothing failed."""
    progress: list[tuple[int, int]] = []
    loaded = await load_inventory(
        staff_client(Faulty()), (10, 11), lambda *done: progress.append(done)
    )
    assert loaded.failed == ()
    assert loaded.inventory.quantities == {
        "MOCK0001": {10: 1},
        "MOCK0003": {10: 2},
        "MOCK0002": {11: 1},
    }
    assert loaded.inventory.attendees["MOCK0002"].allergy == "peanuts"
    assert progress == [(1, 2), (2, 2)]


async def test_a_404_and_a_timeout_fail_their_products_alone() -> None:
    """An unknown product (404) and a timeout are listed; the others are kept."""
    progress: list[tuple[int, int]] = []
    loaded = await load_inventory(
        staff_client(Faulty()), (10, 99, 12, 11), lambda *done: progress.append(done)
    )
    assert loaded.failed == (99, 12)
    assert attendee_count(loaded.inventory) == 3
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]


async def test_an_unreadable_reply_fails_the_product() -> None:
    """A 200 whose body isn't the list counts as failed, as an error does (D-120)."""
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"id": 1}))
    loaded = await load_inventory(staff_client(transport), (10,), lambda *_: None)
    assert loaded == Loaded(Inventory(), (10,))


async def test_a_repeated_id_is_asked_once() -> None:
    """The same product twice is one call, counted once."""
    progress: list[tuple[int, int]] = []
    loaded = await load_inventory(
        staff_client(Faulty()), (10, 10), lambda *done: progress.append(done)
    )
    assert loaded.inventory.quantities["MOCK0003"] == {10: 2}
    assert progress == [(1, 1)]
