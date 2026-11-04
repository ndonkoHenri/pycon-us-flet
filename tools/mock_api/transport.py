"""The mock API behind an `httpx.MockTransport`, for client tests (D-50, D-57).

The request target and the body reach `handle` exactly as the client sent them, so
the signature is checked over the same bytes the client signed. `handle_with_faults`
takes the transport faults on `MockState.faults` around `handle`, for this
transport and `server.py` alike; here each becomes the error `httpx` raises for it
on a real network.
"""

from collections.abc import Mapping

import httpx

from tools.mock_api.faults import Fault
from tools.mock_api.handlers import Reply, handle
from tools.mock_api.state import MockState

BEFORE_HANDLE: tuple[Fault, ...] = ("connect", "timeout")
"""The faults taken before `handle` runs, in order; `lost_response` comes after."""


def handle_with_faults(
    state: MockState,
    method: str,
    raw_path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[Fault | None, Reply | None]:
    """Run `handle` unless a transport fault takes the request first.

    `connect` and `timeout` are taken before `handle` runs, so nothing is
    applied; `lost_response` after, so the request's writes stay but its reply is
    lost. At most one fault is taken per request, the first that is on in that order.

    Args:
        state: The mock's state.
        method: The HTTP method as sent.
        raw_path: The request target exactly as sent.
        headers: The request headers.
        body: The body bytes as sent.

    Returns:
        The fault taken, or None; and `handle`'s reply, or None when it didn't run.
    """
    for fault in BEFORE_HANDLE:
        if state.faults.take(fault):
            return fault, None
    reply = handle(state, method, raw_path, headers, body)
    return ("lost_response" if state.faults.take("lost_response") else None), reply


def mock_transport(state: MockState) -> httpx.MockTransport:
    """Route an `httpx` client's requests to the in-process mock.

    Args:
        state: The mock's state, shared by every request through this transport.

    Returns:
        A transport to pass to `httpx.AsyncClient(transport=...)`.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        """Answer one request with `handle`'s reply, unless a fault takes it.

        Raises:
            httpx.ConnectError: The `connect` fault: no server answered.
            httpx.ReadTimeout: The `timeout` fault: the request went, nothing came
                back.
            httpx.ReadError: The `lost_response` fault: `handle` ran and its
                writes stay, but the reply never arrives.
        """
        fault, reply = handle_with_faults(
            state,
            request.method,
            request.url.raw_path.decode("ascii"),
            request.headers,
            request.content,
        )
        if fault == "connect":
            raise httpx.ConnectError("mock fault: connect", request=request)
        if fault == "timeout":
            raise httpx.ReadTimeout("mock fault: timeout", request=request)
        if fault == "lost_response":
            raise httpx.ReadError("mock fault: lost_response", request=request)
        assert reply is not None  # no fault took it, so handle ran
        status, headers, body = reply
        return httpx.Response(status, headers=headers, content=body)

    return httpx.MockTransport(respond)
