"""The client under the mock's faults: conference Wi-Fi, replayed on demand (D-57).

Each scenario switches a fault on ``MockState`` and calls the real ``ApiClient`` over
``tools/mock_api/transport.py``, so the mock checks every signature and records every
write; the outbox's own scenarios build on these in #38.
"""

import httpx
import pytest

from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.endpoints import CHECK_FEATURES, LEAD_CAPTURE, lead_capture_query
from tests.api_clients import signed_in
from tests.mock_calls import NOW, state_at
from tools.mock_api.faults import Fault, Faults
from tools.mock_api.state import Capture, MockState

ADA = lead_capture_query("MOCK0001", "v4l1d01")
"""A sponsor's own lead capture of the seeded attendee ``MOCK0001``."""


async def capture_ada(client: ApiClient) -> object:
    """Capture ``MOCK0001`` as a lead, the write a lost response makes ambiguous."""
    return await client.request(LEAD_CAPTURE, query=ADA)


@pytest.mark.parametrize("fault", ["connect", "timeout"])
async def test_no_answer_is_a_network_error_and_nothing_is_applied(
    fault: Fault,
) -> None:
    """``connect`` and ``timeout`` give ``NetworkError`` before the mock records a lead."""
    client, _, state = await signed_in("sponsor")
    state.faults.inject(fault)
    with pytest.raises(NetworkError, match=f"mock fault: {fault}") as raised:
        await capture_ada(client)
    assert state.leads == []
    # Sign-in says a timeout apart from being offline (D-54, #684).
    assert raised.value.timed_out is (fault == "timeout")
    # A read timeout may come after the server had it, though this mock had not (D-410).
    assert raised.value.maybe_sent is (fault == "timeout")


async def test_a_lost_response_is_a_network_error_though_the_mock_applied_it() -> None:
    """The mock commits the lead, then the reply is lost: the client can't tell."""
    client, _, state = await signed_in("sponsor")
    state.faults.inject("lost_response")
    with pytest.raises(NetworkError, match="lost_response") as raised:
        await capture_ada(client)
    assert [lead.access_code for lead in state.leads] == ["MOCK0001"]
    assert raised.value.maybe_sent  # so the outbox flags the row (D-410)


@pytest.mark.parametrize(
    ("error", "maybe_sent"),
    [
        (httpx.ConnectError, False),  # DNS failures too
        (httpx.ConnectTimeout, False),
        (httpx.PoolTimeout, False),
        (httpx.ProxyError, False),
        (httpx.UnsupportedProtocol, False),
        (httpx.ReadError, True),
        (httpx.ReadTimeout, True),
        (httpx.WriteError, True),
        (httpx.WriteTimeout, True),
        (httpx.RemoteProtocolError, True),
    ],
)
def test_only_a_request_that_never_left_is_surely_not_sent(
    error: type[httpx.TransportError], maybe_sent: bool
) -> None:
    """``maybe_sent`` is False only for errors raised before a connection existed."""
    assert NetworkError.of(error("down")).maybe_sent is maybe_sent


@pytest.mark.parametrize(
    ("capture", "rows"), [("idempotent", 1), ("non_idempotent", 2)]
)
async def test_replaying_a_lost_capture_duplicates_only_without_idempotency(
    capture: Capture, rows: int
) -> None:
    """The retry after a lost response is one lead when idempotent, two when not.

    The second row under ``non_idempotent`` is the duplicate the outbox must detect
    and show (D-57); no client can prevent it.
    """
    client, _, state = await signed_in("sponsor", state_at(capture))
    state.faults.inject("lost_response")
    with pytest.raises(NetworkError):
        await capture_ada(client)
    reply = await capture_ada(client)
    assert isinstance(reply, dict) and reply["first_name"] == "Ada"
    assert [lead.access_code for lead in state.leads] == ["MOCK0001"] * rows


async def test_a_revoked_key_is_an_auth_error_until_cleared() -> None:
    """``revoked`` kept on refuses every signed call with 401 until it is cleared."""
    client, recorder, state = await signed_in("staff")
    state.faults.inject("revoked", until_cleared=True)
    for _ in range(2):
        with pytest.raises(ApiError) as caught:
            await client.request(CHECK_FEATURES)
        assert (caught.value.is_auth, caught.value.status) == (True, 401)
        assert caught.value.message == "API key revoked."
    state.faults.clear()
    assert await client.request(CHECK_FEATURES)
    assert len(recorder.sent) == 4  # sign-in, two refusals (never retried), then 200


async def test_a_one_shot_revocation_refuses_only_the_next_signed_call() -> None:
    """Sign-in is unsigned, so a one-shot ``revoked`` waits for the next signed call."""
    state = state_at()
    state.faults.inject("revoked")
    client, _, _ = await signed_in("staff", state)
    with pytest.raises(ApiError) as caught:
        await client.request(CHECK_FEATURES)
    assert caught.value.is_auth
    assert await client.request(CHECK_FEATURES)


async def test_a_900_second_skew_is_corrected_by_exactly_one_retry() -> None:
    """``skew`` runs the mock 900 s ahead: 403, one corrected retry, then none."""
    client, recorder, state = await signed_in("attendee")
    state.skew = 900
    assert await client.request(CHECK_FEATURES)
    assert await client.request(CHECK_FEATURES)
    stamps = [request.headers["X-API-Timestamp"] for request in recorder.sent[1:]]
    assert stamps == [str(int(NOW)), str(int(NOW + 900)), str(int(NOW + 900))]
    assert client.skew == 900


async def test_a_fault_kept_on_hits_every_request_until_cleared() -> None:
    """``until_cleared`` keeps ``connect`` on across requests; ``clear`` ends it."""
    client, recorder, state = await signed_in("attendee")
    state.faults.inject("connect", until_cleared=True)
    for _ in range(3):
        with pytest.raises(NetworkError):
            await client.request(CHECK_FEATURES)
    state.faults.clear("connect")
    assert await client.request(CHECK_FEATURES)
    assert len(recorder.sent) == 5


async def test_a_request_takes_one_fault_and_leaves_the_next_for_later() -> None:
    """Two faults on: the first request takes ``connect``, the second the other.

    The first drops before the mock runs, the second commits and loses its reply, and
    the third goes through.
    """
    client, _, state = await signed_in("sponsor")
    state.faults.inject("connect")
    state.faults.inject("lost_response")
    for fault in ("connect", "lost_response"):
        with pytest.raises(NetworkError, match=fault):
            await capture_ada(client)
    assert len(state.leads) == 1
    assert await capture_ada(client)


def test_an_unknown_fault_is_refused() -> None:
    """``inject`` names only the faults the mock models."""
    with pytest.raises(ValueError, match="fault must be one of"):
        Faults().inject("slow")  # type: ignore[arg-type]  # the point of the test


def test_a_fresh_state_has_no_fault_and_no_skew() -> None:
    """A seeded state serves cleanly until a test or ``--fault`` says otherwise."""
    state = MockState.from_seed()
    assert (state.faults.on, state.skew) == ({}, 0.0)
