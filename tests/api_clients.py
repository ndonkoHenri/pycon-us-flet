"""Helpers for the API client's tests: recorded transports and signed-in clients.

The client talks to the mock through `tools/mock_api/transport.py`, so each test runs
the real signature check over the bytes the client sent; `Recorder` keeps those
requests so a test can count them and read what went on the wire.
"""

from collections.abc import Callable

import httpx

from pycon_us.services.api import ApiClient
from pycon_us.services.endpoints import AUTHENTICATE
from tests.mock_calls import NOW, Clock, state_at
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

BASE_URL = "http://mock.test"


class Recorder(httpx.AsyncBaseTransport):
    """A transport that keeps every request it is given, then lets `inner` answer."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Wrap `inner`, with nothing sent yet."""
        self.inner = inner
        self.sent: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request and return `inner`'s reply to it."""
        self.sent.append(request)
        return await self.inner.handle_async_request(request)


def replying(
    status: int, content: bytes, headers: dict[str, str] | None = None
) -> Recorder:
    """A recorded transport that answers every request with this one reply."""
    return Recorder(
        httpx.MockTransport(
            lambda request: httpx.Response(status, headers=headers, content=content)
        )
    )


class ReplyReplaced(httpx.AsyncBaseTransport):
    """A transport that lets `inner` commit each request, then answers `content`.

    What a server that applied a call but answered unusably looks like to the client.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, content: bytes) -> None:
        """Wrap `inner`, whose replies are replaced with `content`."""
        self.inner = inner
        self.content = content

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Let `inner` commit the request, and answer `content` with HTTP 200."""
        await self.inner.handle_async_request(request)
        return httpx.Response(200, content=self.content)


class Login:
    """The credentials a client signs with, as the Account store will hand them over."""

    def __init__(self, key: str | None = None, secret: str | None = None) -> None:
        """Start with these credentials (signed out by default)."""
        self.key = key
        self.secret = secret

    def __call__(self) -> tuple[str | None, str | None]:
        """The key and the secret now."""
        return self.key, self.secret


def client_for(
    transport: httpx.AsyncBaseTransport,
    login: Login | None = None,
    *,
    year: int = 2026,
    base_url: str = BASE_URL,
    now: Callable[[], float] = lambda: NOW,
) -> ApiClient:
    """A client over `transport` whose device clock is fixed (at `NOW` by default)."""
    return ApiClient(base_url, year, login or Login(), transport=transport, now=now)


async def signed_in(
    role: str, state: MockState | None = None, clock: Clock | None = None
) -> tuple[ApiClient, Recorder, MockState]:
    """A client signed in to the mock as the seeded `role`, by `authenticate`.

    Returns:
        The client, the recorder of its requests (sign-in included) and the mock's state.
    """
    state = state or state_at(clock=clock)
    recorder = Recorder(mock_transport(state))
    login = Login()
    client = client_for(recorder, login)
    reply = await client.request(
        AUTHENTICATE,
        payload={"email": f"{role}@example.com", "password": f"mock-{role}"},
    )
    assert isinstance(reply, dict)
    login.key, login.secret = reply["key"], reply["secret"]
    return client, recorder, state
