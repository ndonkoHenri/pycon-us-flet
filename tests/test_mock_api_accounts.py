"""The mock API's account endpoints, called directly and through `mock_transport`.

`authenticate`, `user/check_features` and `user/mobile_state` as
`tools/mock_api/README.md` describes them (API-02, API-03, API-04; D-42, D-55).
"""

import json

import httpx
import pytest

from pycon_us.core.signing import auth_headers, canonical_body
from tools.mock_api.handlers import handle
from tools.mock_api.state import Account, MockState
from tools.mock_api.transport import mock_transport

NOW = 1_780_000_000.0
"""The mock's fixed clock in these tests."""

BASE = "/2026/api/v1/"


def state_at(now: float = NOW) -> MockState:
    """A fresh seeded state whose clock always reads `now`."""
    return MockState.from_seed(now=lambda: now)


def account(state: MockState, role: str) -> Account:
    """The seeded account with this role."""
    return next(a for a in state.accounts if a.role == role)


def call(
    state: MockState, method: str, endpoint: str, payload: object = None, role: str = ""
) -> tuple[int, object]:
    """Send one request to `handle`, signed as `role` unless it is empty.

    Returns:
        The status and the decoded body.
    """
    path = f"{BASE}{endpoint}"
    body = b"" if payload is None else canonical_body(payload)
    headers: dict[str, str] = {}
    if role:
        who = account(state, role)
        signed = auth_headers(who.key, who.secret, NOW, method, path, body)
        headers = {name: str(value) for name, value in signed.items()}
    status, _, reply = handle(state, method, path, headers, body)
    return status, json.loads(reply)


def test_authenticate_returns_the_account_bare_and_needs_no_signature() -> None:
    """The right email and password give nickname, email, key, secret and flags."""
    state = state_at()
    sponsor = account(state, "sponsor")
    login = {"email": sponsor.email, "password": sponsor.password}
    assert call(state, "POST", "authenticate/", login) == (
        200,
        {
            "nickname": "Sam Sponsor",
            "email": "sponsor@example.com",
            "key": "mock-key-sponsor",
            "secret": "mock-secret-sponsor",
            "features": {
                "lead_retrieval": True,
                "door_check_in": False,
                "mask_violation": False,
                "is_speaker": False,
            },
        },
    )


@pytest.mark.parametrize(
    "login",
    [
        {"email": "sponsor@example.com", "password": "wrong"},
        {"email": "nobody@example.com", "password": "mock-sponsor"},
        {"email": "sponsor@example.com", "password": "mock-attendee"},
        {"email": "sponsor@example.com"},
        {},
    ],
)
def test_a_wrong_login_gets_ionics_message(login: dict) -> None:
    """A wrong or missing email or password is 401 with the `message` Ionic shows."""
    assert call(state_at(), "POST", "authenticate/", login) == (
        401,
        {"message": "Invalid email or password."},
    )


@pytest.mark.parametrize("body", [b"", b"not json", b"[]", b'"x"', b"\xff"])
def test_a_body_that_is_not_an_object_is_400(body: bytes) -> None:
    """`authenticate` refuses a body that is not a UTF-8 JSON object with 400."""
    status, _, reply = handle(state_at(), "POST", f"{BASE}authenticate/", {}, body)
    assert (status, json.loads(reply)) == (
        400,
        {"code": 400, "error": "The body must be a JSON object."},
    )


@pytest.mark.parametrize(
    ("role", "features"),
    [
        ("attendee", {"lead_retrieval": False}),
        (
            "speaker",
            dict.fromkeys(("lead_retrieval", "door_check_in", "mask_violation"), False),
        ),
        (
            "sponsor",
            {"lead_retrieval": True, "door_check_in": False, "mask_violation": False},
        ),
        (
            "staff",
            {"lead_retrieval": False, "door_check_in": True, "mask_violation": False},
        ),
        (
            "coc",
            {"lead_retrieval": False, "door_check_in": False, "mask_violation": True},
        ),
        (
            "all",
            dict.fromkeys(("lead_retrieval", "door_check_in", "mask_violation"), True),
        ),
    ],
)
def test_check_features_returns_the_three_flags_absent_ones_left_out(
    role: str, features: dict
) -> None:
    """Each role's flags come back bare, without `is_speaker` and without absent ones."""
    state = state_at()
    assert call(state, "GET", "user/check_features/", role=role) == (
        200,
        {"features": features},
    )


def test_mobile_state_returns_the_seeded_favourites() -> None:
    """A GET returns the account's favourites, bare, as strings."""
    reply = call(state_at(), "GET", "user/mobile_state/", role="attendee")
    assert reply == (200, {"favorites": ["9001", "poster-detail-7"]})


def test_a_patch_replaces_the_list_for_that_account_only() -> None:
    """A PATCH replaces the list (not a merge); integer ids are stored as strings."""
    state = state_at()
    sent = {"favorites": ["poster-detail-7", 123]}
    assert call(state, "PATCH", "user/mobile_state/", sent, role="attendee") == (
        200,
        {"favorites": ["poster-detail-7", "123"]},
    )
    assert call(state, "GET", "user/mobile_state/", role="attendee") == (
        200,
        {"favorites": ["poster-detail-7", "123"]},
    )
    assert call(state, "GET", "user/mobile_state/", role="speaker") == (
        200,
        {"favorites": []},
    )
    assert (
        call(state, "PATCH", "user/mobile_state/", {"favorites": []}, "attendee")[0]
        == 200
    )
    assert account(state, "attendee").favorites == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"favorites": "1"},
        {"favorites": [1.0]},
        {"favorites": [True]},
        {"favorites": [None]},
        [],
    ],
)
def test_a_patch_without_a_list_of_ids_is_400(payload: object) -> None:
    """Floats, booleans, nulls and non-lists are refused, and the list stays as it was."""
    state = state_at()
    status, body = call(state, "PATCH", "user/mobile_state/", payload, role="attendee")
    assert status == 400
    assert isinstance(body, dict) and body["code"] == 400
    assert account(state, "attendee").favorites == ["9001", "poster-detail-7"]


def test_a_patch_with_a_lone_surrogate_is_400_and_keeps_the_list() -> None:
    """An id JSON can escape but UTF-8 can't encode is 400; later GETs still work."""
    state = state_at()
    who = account(state, "attendee")
    path = f"{BASE}user/mobile_state/"
    body = b'{"favorites":["\\ud800"]}'
    signed = auth_headers(who.key, who.secret, NOW, "PATCH", path, body)
    headers = {name: str(value) for name, value in signed.items()}
    status, _, reply = handle(state, "PATCH", path, headers, body)
    assert (status, json.loads(reply)) == (
        400,
        {"code": 400, "error": "favorites must be a list of ids."},
    )
    assert who.favorites == ["9001", "poster-detail-7"]
    assert call(state, "GET", "user/mobile_state/", role="attendee") == (
        200,
        {"favorites": ["9001", "poster-detail-7"]},
    )


def test_each_state_starts_from_the_seed() -> None:
    """A PATCH on one state leaves a state loaded afterwards untouched."""
    first = state_at()
    call(first, "PATCH", "user/mobile_state/", {"favorites": []}, role="attendee")
    assert account(state_at(), "attendee").favorites == ["9001", "poster-detail-7"]


async def test_a_plain_httpx_client_signs_in_and_syncs_through_the_transport() -> None:
    """Sign in, read the flags, then PATCH and GET favourites over `mock_transport`."""
    state = state_at()
    transport = mock_transport(state)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mock.test"
    ) as client:
        login = canonical_body({"email": "coc@example.com", "password": "mock-coc"})
        signed_in = await client.post(f"{BASE}authenticate/", content=login)
        assert signed_in.status_code == 200
        assert "Date" in signed_in.headers
        key, secret = signed_in.json()["key"], signed_in.json()["secret"]

        async def send(method: str, endpoint: str, body: bytes = b"") -> httpx.Response:
            """Send a request signed with the key and secret from sign-in."""
            path = f"{BASE}{endpoint}"
            headers = auth_headers(key, secret, NOW, method, path, body)
            return await client.request(
                method,
                path,
                content=body,
                headers={name: str(value) for name, value in headers.items()},
            )

        flags = await send("GET", "user/check_features/")
        assert flags.json() == {
            "features": {
                "lead_retrieval": False,
                "door_check_in": False,
                "mask_violation": True,
            }
        }
        favourites = canonical_body({"favorites": ["café-☕", "42"]})
        assert (
            await send("PATCH", "user/mobile_state/", favourites)
        ).status_code == 200
        assert (await send("GET", "user/mobile_state/")).json() == {
            "favorites": ["café-☕", "42"]
        }


async def test_the_transport_checks_the_query_exactly_as_sent() -> None:
    """A query signed in one order and sent in another is 403 through the transport."""
    state = state_at()
    who = account(state, "attendee")
    signed_path = f"{BASE}user/mobile_state/?a=1&b=%2F"
    headers = auth_headers(who.key, who.secret, NOW, "GET", signed_path)
    sent = {name: str(value) for name, value in headers.items()}
    async with httpx.AsyncClient(
        transport=mock_transport(state), base_url="http://mock.test"
    ) as client:
        assert (await client.get(signed_path, headers=sent)).status_code == 200
        reordered = f"{BASE}user/mobile_state/?b=%2F&a=1"
        assert (await client.get(reordered, headers=sent)).status_code == 403
