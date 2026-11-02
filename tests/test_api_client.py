"""The signed API client against the mock: round trips, errors and clock skew (D-53).

Every call goes through ``tools/mock_api/transport.py``, so the mock checks each
signature over the exact target and body the client sent.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.endpoints import (
    AUTHENTICATE,
    CHECK_FEATURES,
    COC_ATTENDEES,
    COC_REPORT,
    COC_SCAN,
    ENDPOINTS,
    FETCH_PRODUCTS,
    INVENTORY,
    LEAD_CAPTURE,
    LEAD_NOTE,
    LEAD_SPONSORS,
    READ_MOBILE_STATE,
    REDEEM,
    REDEEMABLE,
    WRITE_MOBILE_STATE,
    Endpoint,
    coc_capture_query,
    fetch_products_query,
    lead_capture_query,
)
from tests.api_clients import (
    Login,
    Recorder,
    ReplyReplaced,
    client_for,
    replying,
    signed_in,
)
from tests.mock_calls import NOW, Clock, state_at
from tools.mock_api.transport import mock_transport

type Check = Callable[[Any], bool]

ROUND_TRIPS: list[tuple[str, Endpoint, tuple[str, ...], str, object, Check]] = [
    ("attendee", CHECK_FEATURES, (), "", None,
     lambda r: r == {"features": {"lead_retrieval": False}}),
    ("attendee", READ_MOBILE_STATE, (), "", None,
     lambda r: r == {"favorites": ["9001", "poster-detail-7"]}),
    ("attendee", WRITE_MOBILE_STATE, (), "", {"favorites": ["café-☕", "42"]},
     lambda r: r == {"favorites": ["café-☕", "42"]}),
    ("staff", REDEEMABLE, (), "", None,
     lambda r: len(r["redeemable_categories"]) == 4),
    ("staff", INVENTORY, ("10",), "", None,
     lambda r: [row["id"] for row in r] == ["MOCK0001", "MOCK0003"]),
    ("staff", FETCH_PRODUCTS, (), fetch_products_query("MOCK0001", [3, 4], door=False),
     None, lambda r: r["attendee_name"] == "Ada Example"),
    ("staff", FETCH_PRODUCTS, (), fetch_products_query("MOCK0003", [10], door=True),
     None, lambda r: r["has_items_to_redeem"] is True),
    ("staff", REDEEM, (), "", {
        "attendee_access_code": "MOCK0001", "badge_validator": "v4l1d01",
        "scanned_at": "2026-05-15T16:00:00.000Z",
        "product-redeem-30": 30, "product-30-quantity": 1,
    }, lambda r: r["errors"] == []),
    ("coc", COC_ATTENDEES, (), "", None, lambda r: len(r) == 4),
    ("coc", COC_SCAN, (), coc_capture_query("MOCK0002"), None,
     lambda r: r["violations"] == 2),
    ("coc", COC_REPORT, (), "", {
        "attendee_access_code": "MOCK0003", "notes": "Second warning", "force": True,
    }, lambda r: r["violations"] == 4),
    ("staff", LEAD_SPONSORS, (), "", None, lambda r: len(r["sponsors"]) == 3),
    ("sponsor", LEAD_CAPTURE, (), lead_capture_query("MOCK0001", "v4l1d01"), None,
     lambda r: r["first_name"] == "Ada"),
    ("staff", LEAD_CAPTURE, (), lead_capture_query("MOCK0002", "v4l1d02", "2"), None,
     lambda r: r["first_name"] == "Grace"),
]  # fmt: skip
"""Role, endpoint, path args, query, payload and what the reply must satisfy."""


@pytest.mark.parametrize(
    ("role", "endpoint", "args", "query", "payload", "check"),
    ROUND_TRIPS,
    ids=[f"{trip[1].method}-{trip[1].name}-{trip[0]}" for trip in ROUND_TRIPS],
)
async def test_each_endpoint_round_trips_through_the_mock(
    role: str,
    endpoint: Endpoint,
    args: tuple[str, ...],
    query: str,
    payload: object,
    check: Check,
) -> None:
    """A signed call is accepted by the mock first time and its reply is unwrapped."""
    client, recorder, _ = await signed_in(role)
    reply = await client.request(endpoint, *args, query=query, payload=payload)
    assert check(reply), reply
    assert len(recorder.sent) == 2  # sign-in, then this call: no retry


def test_the_round_trips_cover_every_endpoint() -> None:
    """Every endpoint but sign-in and the note (tested on their own) has a round trip."""
    covered = {trip[1] for trip in ROUND_TRIPS} | {AUTHENTICATE, LEAD_NOTE}
    assert covered == set(ENDPOINTS)


async def test_a_lead_note_follows_its_capture_with_the_code_in_the_path() -> None:
    """A note posts to ``lead_retrieval/<code>/note/`` after the lead is captured."""
    client, recorder, state = await signed_in("sponsor")
    await client.request(LEAD_CAPTURE, query=lead_capture_query("MOCK0001", "v4l1d01"))
    note = {"accessCode": "MOCK0001", "note": "Interest: hot\nNotes: café"}
    assert await client.request(LEAD_NOTE, "MOCK0001", payload=note) == {
        "code": 200,
        "data": {},
    }
    assert (
        recorder.sent[-1].url.raw_path == b"/2026/api/v1/lead_retrieval/MOCK0001/note/"
    )
    assert len(state.notes) == 1


async def test_a_path_segment_is_percent_encoded() -> None:
    """A path argument is encoded as ``encodeURIComponent`` would (API-11)."""
    recorder = replying(200, b"{}")
    await client_for(recorder).request(LEAD_NOTE, "A/B C", payload={})
    assert (
        recorder.sent[0].url.raw_path == b"/2026/api/v1/lead_retrieval/A%2FB%20C/note/"
    )


async def test_the_wrong_number_of_path_args_is_a_type_error() -> None:
    """``request`` refuses to send when the args don't fill the path's segments."""
    recorder = replying(200, b"{}")
    with pytest.raises(TypeError):
        await client_for(recorder).request(INVENTORY)
    assert recorder.sent == []


async def test_a_wrong_password_is_an_auth_error_with_the_servers_message() -> None:
    """``authenticate`` refused is ``ApiError(401)`` with its ``message``, ``is_auth``."""
    client = client_for(mock_transport(state_at()))
    with pytest.raises(ApiError) as caught:
        await client.request(
            AUTHENTICATE, payload={"email": "coc@example.com", "password": "nope"}
        )
    assert (caught.value.status, caught.value.message) == (
        401,
        "Invalid email or password.",
    )
    assert caught.value.is_auth


async def test_a_wrong_role_is_an_auth_error_sent_once() -> None:
    """A 403 with the clocks in step is not retried, and ``is_auth`` is true."""
    client, recorder, _ = await signed_in("attendee")
    with pytest.raises(ApiError) as caught:
        await client.request(REDEEMABLE)
    assert caught.value.status == 403
    assert caught.value.message == "This account's role can't use this endpoint."
    assert caught.value.is_auth
    assert len(recorder.sent) == 2


async def test_signed_out_the_call_goes_without_a_key_and_is_401() -> None:
    """With no credentials, ``X-API-Key`` is left out and the mock answers 401."""
    recorder = Recorder(mock_transport(state_at()))
    with pytest.raises(ApiError) as caught:
        await client_for(recorder).request(CHECK_FEATURES)
    assert caught.value.status == 401 and caught.value.is_auth
    assert "X-API-Key" not in recorder.sent[0].headers


async def test_an_unknown_attendee_is_an_api_error_that_is_not_auth() -> None:
    """A 404 carries the envelope's ``error`` as its message, and isn't ``is_auth``."""
    client, _, _ = await signed_in("staff")
    query = fetch_products_query("MOCK9999", [3], door=False)
    with pytest.raises(ApiError) as caught:
        await client.request(FETCH_PRODUCTS, query=query)
    assert caught.value.status == 404
    assert not caught.value.is_auth
    assert caught.value.message


@pytest.mark.parametrize(
    ("status", "content", "endpoint", "message"),
    [
        (502, b"<html>bad gateway</html>", CHECK_FEATURES, "Bad Gateway"),
        (None, b"<html>ok</html>", CHECK_FEATURES, "The reply is not JSON."),
        (None, b"\xff\xfe", CHECK_FEATURES, "The reply is not JSON."),
        (None, b'{"code": 200}', COC_ATTENDEES, "The reply has no data."),
        (None, b'{"message": "Saved."}', COC_ATTENDEES, "Saved."),
        (200, b'{"code": 500, "error": "Boom."}', COC_ATTENDEES, "Boom."),
        (200, b'{"code": 500, "error": "Boom."}', CHECK_FEATURES, "Boom."),
        (200, b'{"code": 500, "error": "Boom."}', LEAD_NOTE, "Boom."),
        (500, b'{"code": 500, "error": "Boom."}', CHECK_FEATURES, "Boom."),
        (302, b"", CHECK_FEATURES, "Found"),
    ],
    ids=["html-error", "html-ok", "not-utf8", "no-data", "no-envelope", "error-envelope",
         "error-envelope-bare", "error-envelope-note", "error-status", "redirect-not-followed"],
)  # fmt: skip
async def test_an_unusable_reply_is_an_api_error(
    status: int | None, content: bytes, endpoint: Endpoint, message: str
) -> None:
    """An error status or envelope is a refusal; a success we can't read has no status.

    The server may have applied a call it answered unreadably, so non-JSON or a
    missing envelope is ``status`` None, ``unreadable``, unlike a refusal (#874).
    """
    answer = 200 if status is None else status
    client = client_for(replying(answer, content, {"Location": "/elsewhere/"}))
    with pytest.raises(ApiError) as caught:
        await client.request(endpoint, *(["MOCK0001"] if endpoint is LEAD_NOTE else []))
    assert (caught.value.status, caught.value.message) == (status, message)
    assert caught.value.unreadable == (status is None)


async def test_a_null_reply_to_a_committed_note_is_a_success() -> None:
    """JSON ``null`` from a bare endpoint is returned, so the note isn't sent twice."""
    client, recorder, state = await signed_in("sponsor")
    await client.request(LEAD_CAPTURE, query=lead_capture_query("MOCK0001", "v4l1d01"))
    recorder.inner = ReplyReplaced(recorder.inner, b"null")
    note = {"accessCode": "MOCK0001", "note": "Interest: warm"}
    assert await client.request(LEAD_NOTE, "MOCK0001", payload=note) is None
    assert len(state.notes) == 1


async def test_a_bare_reply_is_returned_whole() -> None:
    """A bare endpoint's reply comes back as decoded, ``code`` and all."""
    client = client_for(replying(200, b'{"code": 200, "data": {"x": 1}}'))
    assert await client.request(CHECK_FEATURES) == {"code": 200, "data": {"x": 1}}


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.ReadError("connection reset"),
    ],
    ids=lambda error: type(error).__name__,
)
async def test_no_answer_is_a_network_error(error: httpx.TransportError) -> None:
    """Every transport error, timeouts included, is ``NetworkError`` naming its type."""

    def fail(request: httpx.Request) -> httpx.Response:
        """Raise the transport error instead of answering."""
        raise error

    client = client_for(httpx.MockTransport(fail))
    with pytest.raises(NetworkError, match=type(error).__name__):
        await client.request(CHECK_FEATURES)


async def test_a_skewed_clock_is_corrected_with_one_retry_and_remembered() -> None:
    """The mock jumps 900 s ahead: 403, one corrected retry accepted, then none."""
    clock = Clock()
    client, recorder, _ = await signed_in("attendee", clock=clock)
    clock.at += 900
    assert await client.request(CHECK_FEATURES)
    stamps = [request.headers["X-API-Timestamp"] for request in recorder.sent[1:]]
    assert stamps == [str(int(NOW)), str(int(NOW + 900))]
    assert client.skew == 900
    await client.request(CHECK_FEATURES)
    assert len(recorder.sent) == 4  # sign-in, refused, retried, then first time


async def test_a_refused_retry_is_not_retried_again() -> None:
    """A wrong secret on a skewed clock: one retry, then ``ApiError(403)``, no third."""
    recorder = Recorder(mock_transport(state_at(clock=Clock(NOW + 900))))
    client = client_for(recorder, Login("mock-key-attendee", "not-the-secret"))
    with pytest.raises(ApiError) as caught:
        await client.request(CHECK_FEATURES)
    assert caught.value.status == 403
    assert len(recorder.sent) == 2


async def test_an_unsigned_call_is_never_retried() -> None:
    """``authenticate`` refused on a skewed clock is answered once, not retried."""
    recorder = Recorder(mock_transport(state_at(clock=Clock(NOW + 900))))
    with pytest.raises(ApiError):
        await client_for(recorder).request(
            AUTHENTICATE, payload={"email": "x@example.com", "password": "x"}
        )
    assert len(recorder.sent) == 1


async def test_a_403_without_a_date_is_not_retried() -> None:
    """With no ``Date`` to learn from, a 403 is final and the skew stays as it was."""
    recorder = replying(403, b'{"code": 403, "error": "Wrong signature."}')
    client = client_for(recorder)
    with pytest.raises(ApiError):
        await client.request(CHECK_FEATURES)
    assert (len(recorder.sent), client.skew) == (1, 0.0)
