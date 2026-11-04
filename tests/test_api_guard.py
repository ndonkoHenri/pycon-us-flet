"""The PSF guard: the client never sends a private-API request to a PSF host (D-51).

Exit criterion 4 of P3: whatever base URL the client is given, a request for any
endpoint to `pycon.org` or a subdomain raises before anything reaches the transport,
while a host that only looks like it goes through.
"""

import httpx
import pytest

from pycon_us.services.api import refuse_private_psf
from pycon_us.services.endpoints import ENDPOINTS, Endpoint
from tests.api_clients import client_for, replying

PSF_BASES = [
    "https://pycon.org",
    "https://us.pycon.org",
    "http://us.pycon.org:8000/prefix",
    "https://US.PyCon.ORG.",
    "https://staging.us.pycon.org",
]
"""Base URLs on the PSF's hosts, letter case, a port, a prefix and a trailing dot."""

LOOK_ALIKES = [
    "https://notpycon.org",
    "https://pycon.org.example.test",
    "https://pycon-org.example.test",
    "http://10.0.2.2:8000",
]
"""Hosts that are not the PSF's, the emulator's route to the laptop among them."""


def args_for(endpoint: Endpoint) -> tuple[str, ...]:
    """Placeholder path segments for an endpoint's `{}`s."""
    return ("1",) * endpoint.path.count("{}")


@pytest.mark.parametrize("base_url", PSF_BASES)
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: f"{e.method}-{e.name}")
async def test_client_refuses_psf_hosts(endpoint: Endpoint, base_url: str) -> None:
    """Every endpoint to a PSF host raises `PermissionError` and sends nothing."""
    recorder = replying(200, b'{"code": 200, "data": {}}')
    client = client_for(recorder, base_url=base_url)
    with pytest.raises(PermissionError, match="private PSF endpoint"):
        await client.request(endpoint, *args_for(endpoint), payload={"a": 1})
    assert recorder.sent == []


@pytest.mark.parametrize("base_url", LOOK_ALIKES)
@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: f"{e.method}-{e.name}")
async def test_client_sends_to_look_alike_hosts(
    endpoint: Endpoint, base_url: str
) -> None:
    """A host that merely contains `pycon.org` is not refused: the request is sent."""
    recorder = replying(200, b'{"code": 200, "data": {}}')
    client = client_for(recorder, base_url=base_url)
    await client.request(endpoint, *args_for(endpoint))
    assert len(recorder.sent) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://us.pycon.org/2026/api/v1/user/mobile_state/",
        "https://us.pycon.org/2026/API/V1/user/",
        "https://us.pycon.org/2026/api%2Fv1/user/",
        "https://pycon.org/api/v1",
    ],
)
def test_the_guard_refuses_any_spelling_of_the_api_path(url: str) -> None:
    """Letter case, an encoded slash and a missing trailing slash are refused alike."""
    with pytest.raises(PermissionError):
        refuse_private_psf(httpx.URL(url))


@pytest.mark.parametrize(
    "url",
    [
        "https://us.pycon.org/2026/schedule/conference.json",
        "https://notpycon.org/2026/api/v1/user/mobile_state/",
        "http://localhost:8000/2026/api/v1/user/mobile_state/",
    ],
)
def test_the_guard_lets_the_public_feed_and_other_hosts_through(url: str) -> None:
    """The public feed on a PSF host, and the API on any other host, pass."""
    refuse_private_psf(httpx.URL(url))
