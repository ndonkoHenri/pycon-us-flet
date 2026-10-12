"""HTTP: the public feed fetch (DATA-01; D-05, D-53).

P0 has one request, an unsigned GET of the year's public feed. P3 adds the signed client
for the local mock of the private API here, with the same two errors, so callers only ever
branch on "no answer" (``NetworkError``) or "a bad answer" (``ApiError``).
"""

import httpx

FEED_TIMEOUT = 10.0
"""Seconds to wait for the feed (connect, each read, the pool), as Ionic did (API-12)."""


class NetworkError(Exception):
    """No answer: no connection, a DNS failure, a dropped connection or a timeout."""


class ApiError(Exception):
    """An answer that cannot be used: an HTTP error status, or a malformed response.

    Attributes:
        status: The HTTP status, or None when the response could not be read at all
            (e.g. too many redirects or an undecodable body).
        message: What went wrong, for the log.
    """

    def __init__(self, status: int | None, message: str) -> None:
        """Create the error.

        Args:
            status: The HTTP status, or None when there is none to report.
            message: What went wrong.
        """
        super().__init__(status, message)
        self.status = status
        self.message = message

    def __str__(self) -> str:
        """Return the status and the message."""
        return self.message if self.status is None else f"{self.status} {self.message}"


async def fetch_feed(
    url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> bytes:
    """Download the public conference feed.

    Args:
        url: The year's ``feed_url`` (``conference.toml``).
        transport: The HTTP transport; tests pass an ``httpx.MockTransport``, the app
            leaves it None.

    Returns:
        The response body exactly as served; the caller parses it.

    Raises:
        NetworkError: No answer arrived (``httpx.TransportError``, timeouts included).
        ApiError: The server answered with an error status, or the answer could not be
            read.
    """
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=FEED_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.TransportError as error:
        raise NetworkError(f"{type(error).__name__}: {error}") from error
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        raise ApiError(status, error.response.reason_phrase) from error
    except httpx.HTTPError as error:  # too many redirects, an undecodable body
        raise ApiError(None, f"{type(error).__name__}: {error}") from error
