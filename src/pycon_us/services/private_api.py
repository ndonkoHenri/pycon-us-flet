"""The session's private-API client, there only while a mock API URL is set (D-51).

``PrivateApi`` holds ``Services.api``: an ``ApiClient`` on the mock base URL that
Developer sets (``Prefs.mock_api_url``, DEV-01), else None, so a normal install has no
client and no code path that could send a private-API request. ``connect()`` rebuilds
it when the URL changes and closes the one it replaces. ``parse_mock_api_url()`` checks
the Developer field, refusing the PSF's hosts as the client does (``refuse_private_psf``),
and ``check_connection()`` is Developer's "Check mock connection": one signed call that
says whether the mock answers, so a device check needs no sign-in yet (#668).
"""

import logging
from urllib.parse import urlsplit

import httpx

from pycon_us.services.api import (
    CHECK_FEATURES,
    ApiClient,
    ApiError,
    NetworkError,
    refuse_private_psf,
)

logger = logging.getLogger(__name__)

CONNECTED = "Connected to the local mock server."
"""What the check says when the mock answered as the private API does."""


def signed_out() -> tuple[None, None]:
    """Return no key and no secret: the credentials until the Account store (#35).

    Signed out, a signed call goes without ``X-API-Key`` and the mock answers 401.
    """
    return None, None


def parse_mock_api_url(text: str) -> str | None:
    """Return the mock API base URL the field names, or None when it is empty (off).

    Args:
        text: An ``http://`` or ``https://`` URL; plain HTTP is the mock on the laptop
            (development.md §6). A final ``/`` is dropped, as the paths start with one.

    Raises:
        ValueError: The text is not such a URL, or it is a PSF host, whose private API
            the app never calls (D-06, D-51); the message is the field's error.
    """
    text = text.strip().rstrip("/")
    if not text:
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Use an http:// or https:// address")
    try:
        refuse_private_psf(httpx.URL(f"{text}/api/v1/"))
    except PermissionError:
        raise ValueError("That is the PSF's server. Use the mock's address") from None
    return text


class PrivateApi:
    """The session's ``ApiClient`` while a mock URL is set, else None (D-51).

    ``Services.api`` reads ``client``. Mutable, unlike ``Services``: the client changes
    when Developer saves or clears the URL.

    Attributes:
        client: The client on ``base_url``, or None while no URL is set.
        base_url: The mock's base URL the client uses, or None.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Start with no client.

        Args:
            transport: The HTTP transport every client gets; tests pass the mock's,
                the app leaves it None.
        """
        self._transport = transport
        self.client: ApiClient | None = None
        self.base_url: str | None = None

    async def connect(self, base_url: str | None, year: int) -> None:
        """Use a client on ``base_url``, or none; the client it replaces is closed.

        The same URL keeps the client, and the clock skew it has learned (D-53).

        Args:
            base_url: The mock's base URL (``parse_mock_api_url()``), or None to turn
                the private API off.
            year: The conference year, the first segment of every path.
        """
        if base_url == self.base_url:
            return
        old, self.client, self.base_url = self.client, None, base_url
        if old is not None:
            await old.aclose()
        if base_url is None:
            logger.info("Private-API features off: no mock API URL")
            return
        self.client = ApiClient(base_url, year, signed_out, transport=self._transport)
        # The address stays out of the log, as the feed URL's does (D-120).
        logger.info("Private-API features on: a mock API URL is set")


async def check_connection(client: ApiClient) -> tuple[str, bool]:
    """Send one signed call and say whether the mock answered as the private API does.

    ``check_features`` signed out reaches the mock's route and its key check, so the
    mock's 401 "Unknown API key." means it is there, on the right year; once signed
    in (#35) it answers 200. Any other answer, or none, is said as the error.

    Args:
        client: ``Services.api``.

    Returns:
        What to say, and whether it is connected.
    """
    try:
        await client.request(CHECK_FEATURES)
    except NetworkError as error:
        logger.info("Mock connection check: no answer")
        return f"No answer from the mock server. {error}", False
    except ApiError as error:
        if error.status != 401:
            logger.info("Mock connection check: refused (%s)", error.status)
            return f"The server answered, but not as the mock does: {error}", False
    except PermissionError as error:  # a stored PSF URL: the guard refuses it (D-51)
        return str(error), False
    logger.info("Mock connection check: connected")
    return CONNECTED, True
