"""The mock API's pure ``handle``: routing, envelopes and the signature check (D-50, D-52).

The contract is ``tools/mock_api/README.md``. The signature check is also run against
the vectors Ionic's own code produced (``tests/fixtures/ionic/signing.json``, #662).
"""

import builtins
import json
import socket
import time
from dataclasses import replace
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

from pycon_us.core.signing import auth_headers, canonical_body
from tools.mock_api.handlers import WINDOW, handle, verify
from tools.mock_api.state import SEED, Account, MockState, Refused

NOW = 1_780_000_000.0
"""The mock's fixed clock in these tests."""

BASE = "/2026/api/v1/"
VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "ionic" / "signing.json").read_text("utf-8")
)["cases"]


def state_at(now: float = NOW) -> MockState:
    """A fresh seeded state whose clock always reads ``now``."""
    return MockState.from_seed(now=lambda: now)


def account(state: MockState, role: str) -> Account:
    """The seeded account with this role."""
    return next(a for a in state.accounts if a.role == role)


def signed(
    who: Account, method: str, path: str, body: bytes = b"", now: float = NOW
) -> dict[str, str]:
    """The three headers Ionic would send for this request, signed at ``now``."""
    headers = auth_headers(who.key, who.secret, now, method, path, body)
    return {name: str(value) for name, value in headers.items()}


def reply_json(reply: tuple[int, dict[str, str], bytes]) -> tuple[int, object]:
    """The status and the decoded body of a reply."""
    status, _, body = reply
    return status, json.loads(body)


def test_the_seed_holds_one_fake_account_per_role() -> None:
    """The seed has the six role accounts, each with example.com mail and mock keys."""
    state = state_at()
    assert SEED.parent == Path(__file__).parent / "fixtures" / "mock"
    assert state.year == 2026
    assert [a.role for a in state.accounts] == [
        "attendee",
        "speaker",
        "sponsor",
        "staff",
        "coc",
        "all",
    ]
    for each in state.accounts:
        assert each.email == f"{each.role}@example.com"
        assert (each.password, each.key, each.secret) == (
            f"mock-{each.role}",
            f"mock-key-{each.role}",
            f"mock-secret-{each.role}",
        )
    assert account(state, "sponsor").sponsor_id == 1


def test_every_reply_is_json_dated_by_the_mock_clock() -> None:
    """A reply, error or not, carries JSON and a ``Date`` header from ``state.now``."""
    for path in (f"{BASE}user/check_features/", "/nowhere"):
        status, headers, _ = handle(state_at(), "GET", path, {}, b"")
        assert status in (401, 404)
        assert headers["Content-Type"] == "application/json"
        assert parsedate_to_datetime(headers["Date"]).timestamp() == NOW


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/nowhere"),
        ("GET", f"{BASE}user/unknown/"),
        ("GET", "/2027/api/v1/user/check_features/"),  # another year
        ("POST", f"{BASE}user/check_features/"),  # another method
        ("GET", f"{BASE}authenticate/"),
        ("GET", f"{BASE}user/check_features"),  # no trailing slash
    ],
)
def test_an_unknown_route_is_404_in_the_error_envelope(method: str, path: str) -> None:
    """Unknown paths, years and methods are 404 ``{code, error}``, even when signed."""
    state = state_at()
    headers = signed(account(state, "attendee"), method, path)
    status, body = reply_json(handle(state, method, path, headers, b""))
    assert status == 404
    assert isinstance(body, dict) and body.keys() == {"code", "error"}
    assert body["code"] == 404


def test_a_signed_route_without_credentials_is_401() -> None:
    """A signed route with no ``X-API-Key`` is 401 ``{code, error}``."""
    reply = handle(state_at(), "GET", f"{BASE}user/check_features/", {}, b"")
    assert reply_json(reply) == (401, {"code": 401, "error": "Unknown API key."})


def test_an_unknown_key_is_401_even_when_signed_right() -> None:
    """A key no account has is 401, whatever the signature."""
    stranger = Account(
        "x", "x@example.com", "x", "X", "mock-key-x", "mock-secret-x", {}
    )
    path = f"{BASE}user/check_features/"
    status, _, _ = handle(state_at(), "GET", path, signed(stranger, "GET", path), b"")
    assert status == 401


@pytest.mark.parametrize(
    "stamp", ["", "soon", "-5", "+1780000000", "01780000000", "١٢"]
)
def test_a_malformed_timestamp_is_403(stamp: str) -> None:
    """Only a plain ASCII decimal timestamp, as Ionic sends, is read; others are 403."""
    state = state_at()
    path = f"{BASE}user/check_features/"
    headers = signed(account(state, "attendee"), "GET", path) | {
        "X-API-Timestamp": stamp
    }
    reply = handle(state, "GET", path, headers, b"")
    assert reply_json(reply) == (
        403,
        {"code": 403, "error": "Missing or malformed timestamp."},
    )


@pytest.mark.parametrize(
    ("stamp", "error"),
    [
        ("9" * 309, "Timestamp outside the window."),
        ("9" * 4301, "Missing or malformed timestamp."),
    ],
    ids=["past-float", "past-int-limit"],
)
def test_a_huge_timestamp_is_403_not_an_error(stamp: str, error: str) -> None:
    """A timestamp too big for a float, or for ``int()``, still gets the dated 403."""
    state = state_at()
    path = f"{BASE}user/check_features/"
    headers = signed(account(state, "attendee"), "GET", path) | {
        "X-API-Timestamp": stamp
    }
    reply = handle(state, "GET", path, headers, b"")
    assert reply_json(reply) == (403, {"code": 403, "error": error})
    assert parsedate_to_datetime(reply[1]["Date"]).timestamp() == NOW


@pytest.mark.parametrize(
    ("offset", "status"),
    [(-WINDOW - 1, 403), (-WINDOW, 200), (0, 200), (WINDOW, 200), (WINDOW + 1, 403)],
)
def test_the_window_is_600_seconds_either_side(offset: int, status: int) -> None:
    """A timestamp at most 600 s from the mock's clock passes; one second more is 403."""
    state = state_at()
    path = f"{BASE}user/check_features/"
    headers = signed(account(state, "speaker"), "GET", path, now=NOW + offset)
    assert WINDOW == 600
    assert handle(state, "GET", path, headers, b"")[0] == status


def test_a_wrong_signature_is_403() -> None:
    """A signature made with another secret is 403 ``{code, error}``."""
    state = state_at()
    path = f"{BASE}user/mobile_state/"
    who = account(state, "attendee")
    forged = replace(who, secret="guess")
    reply = handle(state, "GET", path, signed(forged, "GET", path), b"")
    assert reply_json(reply) == (403, {"code": 403, "error": "Wrong signature."})


def test_a_non_ascii_signature_is_403_not_an_error() -> None:
    """A signature header with non-ASCII text is compared safely and refused."""
    state = state_at()
    path = f"{BASE}user/mobile_state/"
    headers = signed(account(state, "attendee"), "GET", path) | {"X-API-Signature": "é"}
    assert handle(state, "GET", path, headers, b"")[0] == 403


def test_header_names_are_read_in_any_case() -> None:
    """Lower-case header names, as ``httpx`` gives them, are read like Ionic's."""
    state = state_at()
    path = f"{BASE}user/mobile_state/"
    headers = signed(account(state, "attendee"), "GET", path)
    lower = {name.lower(): value for name, value in headers.items()}
    assert handle(state, "GET", path, lower, b"")[0] == 200


def test_a_request_signed_for_one_path_is_refused_on_another() -> None:
    """Headers signed for ``mobile_state`` replayed on ``check_features`` are 403."""
    state = state_at()
    headers = signed(account(state, "attendee"), "GET", f"{BASE}user/mobile_state/")
    path = f"{BASE}user/check_features/"
    assert handle(state, "GET", path, headers, b"")[0] == 403


def vector(name: str) -> tuple[MockState, str, str, dict, bytes]:
    """A vector's request and a state at its clock with one account for its key."""
    case = next(case for case in VECTORS if case["name"] == name)
    now = case["now_ms"] / 1000
    who = Account("v", "v@example.com", "-", "V", case["key"], case["secret"], {})
    state = MockState(2027, [who], lambda: now)
    return state, case["method"], case["path"], case["headers"], case["body"].encode()


@pytest.mark.parametrize("name", [case["name"] for case in VECTORS])
def test_every_ionic_vector_passes_the_signature_check(name: str) -> None:
    """Each request Ionic's code signed is accepted at its clock (#662); signed out, 401."""
    state, method, path, headers, body = vector(name)
    if headers["X-API-Key"] is None:  # signed out: Ionic sends a null key
        with pytest.raises(Refused) as refused:
            verify(state, state.now(), method, path, headers, body)
        assert refused.value.status == 401
    else:
        assert verify(state, state.now(), method, path, headers, body).role == "v"


@pytest.mark.parametrize(
    "name", ["get-empty-body", "patch-favorites", "round-half-even", "round-half-odd"]
)
def test_an_ionic_vector_on_an_account_route_gets_200(name: str) -> None:
    """``handle`` answers 200 to the vectors whose routes this issue serves."""
    assert handle(*vector(name))[0] == 200


def test_changing_any_signed_part_of_a_vector_is_refused() -> None:
    """Another method, path, query order, body byte or timestamp gives 403."""
    state, method, path, headers, body = vector("patch-favorites")
    stamp = str(int(state.now()) + 1)
    _, get, query_path, query_headers, _ = vector("get-query-encoded")
    reordered = vector("get-query-encoded-reordered")[2]
    tampered = [
        ("POST", path, headers, body),
        (method, path.replace("mobile_state", "check_features"), headers, body),
        (method, path, headers, body.replace(b'","', b'", "')),
        (method, path, headers | {"X-API-Timestamp": stamp}, body),
        (get, reordered, query_headers, b""),
    ]
    verify(state, state.now(), method, path, headers, body)
    verify(state, state.now(), get, query_path, query_headers, b"")
    for method_, path_, headers_, body_ in tampered:
        with pytest.raises(Refused) as refused:
            verify(state, state.now(), method_, path_, headers_, body_)
        assert refused.value.status == 403


def test_handle_does_no_io_and_reads_only_the_injected_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With files, sockets and the system clock blocked, every route still answers."""
    state = state_at()

    def blocked(*args: object, **kwargs: object) -> None:
        """Fail the test: ``handle`` reached for I/O or the system clock."""
        raise AssertionError("handle did I/O or read the system clock")

    for name in ("time", "time_ns", "monotonic", "localtime", "gmtime"):
        monkeypatch.setattr(time, name, blocked)
    monkeypatch.setattr(builtins, "open", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    who = account(state, "attendee")
    body = canonical_body({"favorites": ["1"]})
    login = canonical_body({"email": who.email, "password": who.password})
    requests = [
        ("POST", f"{BASE}authenticate/", {}, login),
        ("GET", f"{BASE}user/check_features/", None, b""),
        ("GET", f"{BASE}user/mobile_state/", None, b""),
        ("PATCH", f"{BASE}user/mobile_state/", None, body),
        ("GET", "/nowhere", {}, b""),
    ]
    for method, path, headers, sent in requests:
        headers = signed(who, method, path, sent) if headers is None else headers
        assert handle(state, method, path, headers, sent)[0] in (200, 404)
