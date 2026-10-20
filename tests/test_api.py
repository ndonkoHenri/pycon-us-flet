"""Tests for the public feed fetch and its two errors (DATA-01; D-53).

Every response comes from an ``httpx.MockTransport``, never the network.
"""

import httpx
import pytest

from pycon_us.services.api import FEED_TIMEOUT, ApiError, NetworkError, fetch_feed

URL = "https://us.pycon.org/2026/schedule/conference.json"


async def test_the_feed_is_returned_byte_for_byte() -> None:
    """The feed's bytes come back unchanged, from one GET of the feed URL."""
    body = '{"schedule": [], "note": "café"}'.encode()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=body)

    assert await fetch_feed(URL, transport=httpx.MockTransport(handle)) == body
    assert [(request.method, str(request.url)) for request in seen] == [("GET", URL)]


async def test_the_request_waits_ten_seconds_at_most() -> None:
    """The request's connect, read, write and pool timeouts are all 10 seconds."""
    timeouts = []

    def handle(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, content=b"{}")

    await fetch_feed(URL, transport=httpx.MockTransport(handle))
    assert FEED_TIMEOUT == 10.0
    assert timeouts == [dict.fromkeys(("connect", "read", "write", "pool"), 10.0)]


async def test_a_redirect_is_followed() -> None:
    """A 301 to another path is followed, and that path's body is returned."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/moved.json"):
            return httpx.Response(200, content=b"{}")
        return httpx.Response(301, headers={"Location": "/2026/moved.json"})

    assert await fetch_feed(URL, transport=httpx.MockTransport(handle)) == b"{}"


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("no route to host"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.ReadError("connection reset"),
        httpx.RemoteProtocolError("server disconnected"),
    ],
    ids=lambda error: type(error).__name__,
)
async def test_no_answer_is_a_network_error(error: httpx.TransportError) -> None:
    """A transport error raises ``NetworkError`` naming the error's type."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(NetworkError, match=type(error).__name__):
        await fetch_feed(URL, transport=httpx.MockTransport(handle))


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_an_error_status_is_an_api_error_with_its_status(status: int) -> None:
    """A 404, 500 or 503 raises ``ApiError`` with that status, first in its message."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=b"<html>down</html>")

    with pytest.raises(ApiError) as caught:
        await fetch_feed(URL, transport=httpx.MockTransport(handle))
    assert caught.value.status == status
    assert str(caught.value).startswith(f"{status} ")


async def test_a_redirect_loop_is_an_api_error_without_a_status() -> None:
    """A redirect loop raises ``ApiError`` for ``TooManyRedirects``, with no status."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": URL})

    with pytest.raises(ApiError, match="TooManyRedirects") as caught:
        await fetch_feed(URL, transport=httpx.MockTransport(handle))
    assert caught.value.status is None
