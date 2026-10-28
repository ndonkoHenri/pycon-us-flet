"""Tests for the session's private-API client and the mock API URL (D-51, #668).

``services/private_api.py`` builds ``Services.api`` only while a mock URL is set, checks
the Developer field and runs the connection check; the stored URL is ``Prefs``'. The
check runs against the mock itself, through ``tools/mock_api/transport.py``.
"""

import json
from pathlib import Path

import httpx
import pytest

from pycon_us.prefs import Prefs
from pycon_us.services.api import CHECK_FEATURES, ApiClient
from pycon_us.services.private_api import (
    CONNECTED,
    PrivateApi,
    check_connection,
    parse_mock_api_url,
)
from pycon_us.services.storage import Storage
from tests.api_clients import Recorder, replying
from tests.fakes import MemoryPrefs
from tests.mock_calls import state_at
from tools.mock_api.transport import mock_transport

MOCK = "http://10.0.2.2:8000"


@pytest.fixture
def recorder() -> Recorder:
    """A transport to the seeded mock that keeps every request sent through it."""
    return Recorder(mock_transport(state_at()))


async def connected(transport: httpx.AsyncBaseTransport, url: str = MOCK) -> ApiClient:
    """Return the client a ``PrivateApi`` over ``transport`` builds on ``url``."""
    private_api = PrivateApi(transport)
    await private_api.connect(url, 2026)
    assert private_api.client is not None
    return private_api.client


# ------------------------------------------------------------------ the field


@pytest.mark.parametrize(
    ("text", "url"),
    [
        ("", None),
        ("   ", None),
        (" http://10.0.2.2:8000/ ", "http://10.0.2.2:8000"),
        ("https://mock.example.test/prefix", "https://mock.example.test/prefix"),
    ],
)
def test_the_field_takes_an_http_url_or_nothing(text: str, url: str | None) -> None:
    """Empty is off; a URL loses its spaces and final slash, the paths bring their own."""
    assert parse_mock_api_url(text) == url


@pytest.mark.parametrize("text", ["10.0.2.2:8000", "ftp://mock.test", "http://"])
def test_the_field_refuses_what_is_not_an_http_url(text: str) -> None:
    """A URL without an http(s) scheme or a host is the field's error."""
    with pytest.raises(ValueError, match="http:// or https://"):
        parse_mock_api_url(text)


@pytest.mark.parametrize(
    "text",
    ["https://us.pycon.org", "https://PyCon.org./", "http://us.pycon.org:8000/x"],
)
def test_the_field_refuses_the_psf_s_hosts(text: str) -> None:
    """A PSF host is refused by the client's own guard, whatever its case (D-51)."""
    with pytest.raises(ValueError, match="PSF"):
        parse_mock_api_url(text)


# ------------------------------------------------------------------ the pref


async def test_the_mock_api_url_round_trips_through_storage(tmp_path: Path) -> None:
    """A saved URL reads back after a load, and turns the private API on."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    await Prefs().save(storage, dev={"unlocked": True, "mock_api_url": MOCK})
    prefs = Prefs()
    await prefs.load(storage)
    assert prefs.mock_api_url == MOCK
    assert prefs.private_api_enabled is True
    assert prefs.developer_unlocked is True  # the other options are kept


@pytest.mark.parametrize("value", [None, "", 8000, ["http://mock.test"]])
def test_no_url_or_a_wrong_one_leaves_the_private_api_off(value: object) -> None:
    """An absent, empty or wrongly typed value reads as no URL (D-187's rule)."""
    prefs = Prefs(dev={} if value is None else {"mock_api_url": value})
    assert prefs.mock_api_url is None
    assert prefs.private_api_enabled is False


# ------------------------------------------------------------------ the client


async def test_there_is_no_client_until_a_url_is_set() -> None:
    """A fresh ``PrivateApi`` has no client, so nothing can send a request (D-51)."""
    private_api = PrivateApi()
    assert (private_api.client, private_api.base_url) == (None, None)
    await private_api.connect(None, 2026)
    assert private_api.client is None


async def test_a_new_url_replaces_the_client_and_closes_the_old_one(
    recorder: Recorder,
) -> None:
    """Another URL builds a new client; clearing leaves none; each old one is closed."""
    private_api = PrivateApi(recorder)
    await private_api.connect(MOCK, 2026)
    first = private_api.client
    assert first is not None
    await private_api.connect(MOCK, 2026)
    assert private_api.client is first  # the same URL keeps it, and its skew (D-53)
    await private_api.connect("http://localhost:8000", 2026)
    second = private_api.client
    assert second is not None and second is not first
    assert first._http.is_closed
    await private_api.connect(None, 2026)
    assert private_api.client is None and private_api.base_url is None
    assert second._http.is_closed


async def test_a_stored_psf_url_still_cannot_send_a_private_request(
    recorder: Recorder,
) -> None:
    """A PSF URL that got into the pref past the field builds a client that refuses.

    The client's guard raises before anything reaches the transport (#665), and the
    check says so instead of reporting a connection.
    """
    client = await connected(recorder, "https://us.pycon.org")
    with pytest.raises(PermissionError):
        await client.request(CHECK_FEATURES)
    text, ok = await check_connection(client)
    assert (ok, text.startswith("Refusing a private PSF endpoint")) == (False, True)
    assert recorder.sent == []


# ------------------------------------------------------------------ the check


async def test_the_check_says_connected_when_the_mock_answers(
    recorder: Recorder,
) -> None:
    """Signed out, one signed ``check_features`` gets the mock's 401: it is there."""
    assert await check_connection(await connected(recorder)) == (CONNECTED, True)
    (request,) = recorder.sent
    assert request.url.raw_path == b"/2026/api/v1/user/check_features/"
    assert "X-API-Signature" in request.headers


async def test_the_check_says_when_nothing_answers() -> None:
    """No answer (a refused connection) is said with the transport's words."""

    def refuse(request: httpx.Request) -> httpx.Response:
        """Fail as a closed port does."""
        raise httpx.ConnectError("Connection refused", request=request)

    text, ok = await check_connection(await connected(httpx.MockTransport(refuse)))
    assert not ok
    assert text == "No answer from the mock server. ConnectError: Connection refused"


async def test_the_check_says_when_another_server_answers() -> None:
    """A server that is not the mock (a 404 for the route) is not a connection."""
    body = json.dumps({"error": "No route for GET /2026/api/v1/user/check_features/."})
    text, ok = await check_connection(await connected(replying(404, body.encode())))
    assert not ok
    assert text.startswith(
        "The server answered, but not as the mock does: 404 No route"
    )
