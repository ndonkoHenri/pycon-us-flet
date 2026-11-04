"""The public conference feed's fetch: one unsigned GET (D-05, D-53).

`fetch_feed` is the app's only request to the public feed and sends nothing of the
account's: no signature, no key. The private API is `services/api.py`'s signed client,
which refuses the PSF's hosts (D-51); this module cannot reach it. Both raise the same
two errors, `NetworkError` and `ApiError`, which stay in `services/api.py`.
"""

import httpx

from pycon_us.services.api import ApiError, NetworkError

FEED_TIMEOUT = 10.0
"""Seconds to wait for the feed (connect, each read, the pool), as Ionic did (API-12)."""


async def fetch_feed(
    url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> bytes:
    """Download the public conference feed.

    Args:
        url: The year's `feed_url` (`conference.toml`).
        transport: The HTTP transport; tests pass an `httpx.MockTransport`, the app
            leaves it None.

    Returns:
        The response body exactly as served; the caller parses it.

    Raises:
        NetworkError: No answer arrived (`httpx.TransportError`, timeouts included).
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
        raise NetworkError.of(error) from error
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        raise ApiError(status, error.response.reason_phrase) from error
    except httpx.HTTPError as error:  # too many redirects, an undecodable body
        raise ApiError(None, f"{type(error).__name__}: {error}") from error
