"""The signed client of the private API, and the two errors every HTTP call raises (D-05, D-53).

`ApiClient` is the only way the app talks to the private API, which it only ever
reaches on the local mock (D-06): `ApiClient.request` refuses the PSF's hosts before
sending (D-51), signs the exact bytes it sends (D-52) and corrects its clock once from
the server's `Date` (D-53). It and the public feed's fetch (`services/feed_api.py`)
raise the same two errors, so callers only ever branch on "no answer" (`NetworkError`)
or "a bad answer" (`ApiError`). The endpoints and their timeouts are
`services/endpoints.py`'s, after Ionic's `pycon-api.ts`.
"""

import json
import time
from collections.abc import Callable
from datetime import UTC
from email.utils import parsedate_to_datetime

import httpx

from pycon_us.core.signing import canonical_body, enc, js_round, sign
from pycon_us.services.endpoints import Endpoint

SKEW_LIMIT = 300.0
"""Seconds between a refused request's timestamp and the server's `Date` past which
the refusal is blamed on the clock and retried once, corrected (half of the 600 s window
the 2019 server allowed)."""

type Credentials = Callable[[], tuple[str | None, str | None]]
"""Returns the signed-in account's API key and secret, or Nones when signed out."""


NOT_SENT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
)
"""The transport errors raised before a request can have left: no connection was made
(DNS failures are `ConnectError`s). Any other may come after the server got it."""


class NetworkError(Exception):
    """No answer: no connection, a DNS failure, a dropped connection or a timeout.

    Attributes:
        timed_out: Whether the wait ran out (`httpx.TimeoutException`), which
            sign-in says apart from being offline (D-54).
        maybe_sent: Whether the request may have reached the server, which may then
            have applied it though no answer came back (a read error or timeout, a
            dropped connection); False only when it surely never left (`NOT_SENT`).
            The outbox flags such a row "may be recorded twice" (D-57, D-410).
    """

    def __init__(
        self, message: str, *, timed_out: bool = False, maybe_sent: bool = False
    ) -> None:
        """Create the error.

        Args:
            message: What happened, for the log.
            timed_out: Whether the request timed out rather than found no server.
            maybe_sent: Whether the request may have reached the server.
        """
        super().__init__(message)
        self.timed_out = timed_out
        self.maybe_sent = maybe_sent

    @classmethod
    def of(cls, error: httpx.TransportError) -> NetworkError:
        """Return the error for `httpx`'s: a timeout or not, maybe sent or not."""
        return cls(
            f"{type(error).__name__}: {error}",
            timed_out=isinstance(error, httpx.TimeoutException),
            maybe_sent=not isinstance(error, NOT_SENT),
        )


class ApiError(Exception):
    """An answer that cannot be used: the server's refusal, or a reply we can't read.

    Attributes:
        status: The HTTP status of a refusal (an error status, or an error envelope
            under a success), or None when the reply could not be read (`unreadable`).
        message: What went wrong: the server's own `error` or `message` when it sent
            one. The app doesn't control that text, and `str()` includes it, so a
            private-API call logs `status` instead (D-72).
    """

    def __init__(self, status: int | None, message: str) -> None:
        """Create the error.

        Args:
            status: The refusal's HTTP status, or None for a reply that can't be read.
            message: What went wrong.
        """
        super().__init__(status, message)
        self.status = status
        self.message = message

    def __str__(self) -> str:
        """Return the status and the message."""
        return self.message if self.status is None else f"{self.status} {self.message}"

    @property
    def is_auth(self) -> bool:
        """Whether the server refused the credentials or the role (401 or 403).

        The mock answers 401 for an unknown key and 403 for a bad signature, a stale
        timestamp or a wrong role; Ionic never told them apart, so callers treat both
        alike (`tools/mock_api/README.md`, Unknown).
        """
        return self.status in (401, 403)

    @property
    def unreadable(self) -> bool:
        """Whether a reply came that says nothing: the call may have been applied.

        Not JSON, no envelope, an undecodable body or a shape the caller can't parse,
        unlike a refusal, which says the server didn't apply it. So a write must treat
        this as `NetworkError.maybe_sent`: "not confirmed", never "not recorded" (D-410).
        """
        return self.status is None


def refuse_private_psf(url: httpx.URL) -> None:
    """Make calling the PSF's private API impossible, even by misconfiguration (D-51).

    Args:
        url: The full URL a request is about to be sent to.

    Raises:
        PermissionError: The URL is an `/api/v1` path on `pycon.org` or one of its
            subdomains, whatever the letter case or a trailing dot. It is a refused
            misconfiguration, not an answer, so it is neither of the two API errors.
    """
    host = url.host.rstrip(".").lower()
    psf = host == "pycon.org" or host.endswith(".pycon.org")
    if psf and "/api/v1" in url.path.lower():
        raise PermissionError(f"Refusing a private PSF endpoint: {host}{url.path}")


def server_time(date: str | None) -> float | None:
    """Read a reply's `Date` header as seconds since the epoch.

    Args:
        date: The header's value, or None when there is none.

    Returns:
        The server's time, or None when the header is missing or unreadable.
    """
    if not date:
        return None
    try:
        when = parsedate_to_datetime(date)
    except TypeError, ValueError:
        return None
    # "-0000" means UTC with no zone named; timestamp() would read a naive time as local.
    return (when if when.tzinfo else when.replace(tzinfo=UTC)).timestamp()


def error_message(body: object) -> str | None:
    """The server's own words for an error: `error` (signed calls), else `message`.

    Args:
        body: A decoded reply.

    Returns:
        The message, or None when the body carries none.
    """
    if isinstance(body, dict):
        for name in ("error", "message"):
            if isinstance(body.get(name), str):
                return body[name]
    return None


NOT_JSON = object()
"""Stands for a reply that does not decode, unlike a JSON `null`."""

MAX_NESTING = 32
"""How many levels of values a reply may nest; the private API's use a handful. A deeper
one is not read: the parser may take it, but printing it or dumping it into an outbox row
takes more stack, by how much depends on the stack, and neither guards against that (#891).
This is far below what even a small stack overflows at."""


def _decoded(content: bytes) -> object:
    """Return a reply's JSON, or `NOT_JSON`: not UTF-8, not JSON, or nested too deep."""
    try:
        body = json.loads(content)
    except ValueError, RecursionError:
        return NOT_JSON
    level = [body]
    for _ in range(MAX_NESTING):
        level = [
            child
            for parent in level
            if isinstance(parent, dict | list)
            for child in (parent.values() if isinstance(parent, dict) else parent)
        ]
    return NOT_JSON if level else body


def unwrap(response: httpx.Response, enveloped: bool) -> object:
    """Turn a reply into what the caller reads, or an `ApiError`.

    Args:
        response: The reply, read in full.
        enveloped: Whether a success is `{"code", "data"}` and the `data` is wanted.

    Returns:
        The decoded body (JSON `null` included), or its `data` when `enveloped`.

    Raises:
        ApiError: A refusal: an error status (with the body's `error` or `message`
            when it has one) or a `{"code", "error"}` envelope whatever the status.
            Or `unreadable`: a success whose body is not JSON, nests deeper than
            `MAX_NESTING` or has no envelope, which the server may have applied (#874).
    """
    body = _decoded(response.content)
    status = response.status_code
    if not response.is_success:
        raise ApiError(status, error_message(body) or response.reason_phrase)
    if body is NOT_JSON:
        raise ApiError(None, "The reply is not JSON.")
    # An error envelope is a refusal even under HTTP 200 (#665).
    if isinstance(body, dict) and "code" in body and isinstance(body.get("error"), str):
        raise ApiError(status, body["error"])
    if not enveloped:
        return body
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    raise ApiError(None, error_message(body) or "The reply has no data.")


class ApiClient:
    """Signed requests to the private API, byte-compatible with Ionic (D-52, D-53).

    Every private-API call in the app goes through `request`. Redirects are never
    followed: a redirected request would need a new signature.
    """

    def __init__(
        self,
        base_url: str,
        year: int,
        credentials: Credentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Create the client.

        Args:
            base_url: The server's scheme, host, port and any path prefix.
            year: The conference year, the first segment of every path.
            credentials: Returns the key and secret to sign with, read on each request.
            transport: The HTTP transport; tests pass `mock_transport`, the app
                leaves it None.
            now: The device clock in seconds since the epoch; tests fix it.
        """
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport)
        self._year = year
        self._credentials = credentials
        self._now = now
        self.skew = 0.0
        """The server's clock minus the device's, from the last `Date` read."""

    async def aclose(self) -> None:
        """Close the client's connections."""
        await self._http.aclose()

    async def request(
        self,
        endpoint: Endpoint,
        *args: str | int,
        query: str = "",
        payload: object = None,
    ) -> object:
        """Send one call and return its reply.

        The body is serialised once and the signature covers `request.url.raw_path`,
        exactly the target sent. A signed call refused with 403 while its timestamp was
        more than `SKEW_LIMIT` from the server's `Date` is sent once more with the
        corrected clock, which later calls keep using. The credentials are read once,
        so both attempts carry the same key even if the account changes in between
        (D-56: a row only ever goes with its own owner's key).

        Args:
            endpoint: The call.
            *args: The path's `{}` segments in order, percent-encoded here (API-11).
            query: The query from `services/endpoints.py`'s builders, built the Ionic way; never
                `httpx`'s `params=`, which would encode it its own way.
            payload: The JSON body, or None for none.

        Returns:
            The decoded reply, or its `data` for an enveloped endpoint.

        Raises:
            NetworkError: No answer arrived (`httpx.TransportError`, timeouts
                included).
            ApiError: The server refused the call, or its reply could not be read.
            PermissionError: The URL is the PSF's private API (`refuse_private_psf`).
            TypeError: `args` doesn't fill the path's segments.
        """
        if endpoint.path.count("{}") != len(args):
            raise TypeError(f"{endpoint.name} takes {endpoint.path.count('{}')} args")
        path = endpoint.path.format(*(enc(str(arg)) for arg in args))
        target = f"/{self._year}/api/v1/{path}" + (f"?{query}" if query else "")
        body = b"" if payload is None else canonical_body(payload)
        credentials = self._credentials()
        response, skewed = await self._attempt(endpoint, target, body, credentials)
        if endpoint.signed and response.status_code == 403 and skewed:
            # Clock corrected; the same key, whatever the account is now.
            response, _ = await self._attempt(endpoint, target, body, credentials)
        return unwrap(response, endpoint.enveloped)

    async def _attempt(
        self,
        endpoint: Endpoint,
        target: str,
        body: bytes,
        credentials: tuple[str | None, str | None],
    ) -> tuple[httpx.Response, bool]:
        """Build, check, sign and send one request, and learn the skew from its reply.

        Args:
            endpoint: The call.
            target: The path and query to send.
            body: The body bytes, empty for none.
            credentials: The key and secret to sign with, read once per call.

        Returns:
            The reply, and whether the timestamp sent was more than `SKEW_LIMIT` from
            the reply's `Date`.
        """
        request = self._http.build_request(
            endpoint.method, target, content=body or None, timeout=endpoint.timeout
        )
        refuse_private_psf(request.url)
        if body:
            request.headers["Content-Type"] = "application/json"
        stamp = js_round(self._now() + self.skew)
        if endpoint.signed:
            self._sign(request, stamp, body, credentials)
        response = await self._send(request)
        server = server_time(response.headers.get("Date"))
        if server is None:
            return response, False
        self.skew = server - self._now()
        return response, abs(server - stamp) > SKEW_LIMIT

    def _sign(
        self,
        request: httpx.Request,
        stamp: int,
        body: bytes,
        credentials: tuple[str | None, str | None],
    ) -> None:
        """Add the `X-API-*` headers, signed over the target exactly as it is sent.

        Signed out (no key), the request goes without `X-API-Key` and the server
        answers 401.
        """
        key, secret = credentials
        target = request.url.raw_path.decode("ascii")
        request.headers["X-API-Timestamp"] = str(stamp)
        request.headers["X-API-Signature"] = sign(
            secret, stamp, request.method, target, body
        )
        if key is not None:
            request.headers["X-API-Key"] = key

    async def _send(self, request: httpx.Request) -> httpx.Response:
        """Send a request and read its reply, raising the module's two errors.

        Raises:
            NetworkError: No answer arrived.
            ApiError: The reply could not be read (e.g. an undecodable body).
        """
        try:
            return await self._http.send(request)
        except httpx.TransportError as error:  # timeouts included
            raise NetworkError.of(error) from error
        except httpx.HTTPError as error:
            raise ApiError(None, f"{type(error).__name__}: {error}") from error
