"""The mock's LAN server: ``handle`` over a real socket, its log and its banner (#666).

The server runs in-process on ``127.0.0.1`` with an ephemeral port; these tests are
marked ``loopback``, ``no_network``'s one opt-out, which lets httpx reach 127.0.0.1 and
nothing else.
"""

import socket
import threading
from collections.abc import Iterator
from email.utils import formatdate

import httpx
import pytest

from pycon_us.core.signing import auth_headers, canonical_body
from tests.mock_calls import BASE, NOW, account, state_at
from tools.mock_api.server import MockServer, banner
from tools.mock_api.state import MockState

pytestmark = pytest.mark.loopback


@pytest.fixture
def state() -> MockState:
    """A fresh seeded state on the fixed clock ``NOW``."""
    return state_at()


@pytest.fixture
def served(state: MockState) -> Iterator[httpx.Client]:
    """Serve ``state`` on 127.0.0.1 in a thread; yield a client for it, then stop it."""
    with MockServer(("127.0.0.1", 0), state) as server:
        thread = threading.Thread(target=server.serve_forever, args=(0.05,))
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with httpx.Client(base_url=base) as client:
                yield client
        finally:
            server.shutdown()
            thread.join()


def signed(
    state: MockState, role: str, method: str, path: str, body: bytes = b""
) -> dict[str, str]:
    """The three signing headers for ``role``'s request, as the app sends them."""
    who = account(state, role)
    headers = auth_headers(who.key, who.secret, state.now(), method, path, body)
    return {name: str(value) for name, value in headers.items()}


def raw_request(served: httpx.Client, request: str) -> bytes:
    """Send ``request`` as raw bytes (httpx won't send a malformed one); return the status."""
    port = served.base_url.port
    assert port is not None
    with socket.create_connection(("127.0.0.1", port)) as raw:
        raw.sendall(request.encode())
        return raw.makefile("rb").readline().split()[1]


def log_lines(capfd: pytest.CaptureFixture[str]) -> list[str]:
    """The server's log lines written since the last read."""
    return capfd.readouterr().err.splitlines()


def test_a_signed_request_is_answered_over_the_socket(
    state: MockState, served: httpx.Client
) -> None:
    """A signed GET reaches ``handle`` over a real socket and gets its bare reply."""
    path = f"{BASE}user/check_features/"
    reply = served.get(path, headers=signed(state, "staff", "GET", path))
    assert reply.status_code == 200
    assert reply.json() == {
        "features": {
            "lead_retrieval": False,
            "door_check_in": True,
            "mask_violation": False,
        }
    }


def test_a_signed_body_arrives_byte_for_byte(
    state: MockState, served: httpx.Client
) -> None:
    """A PATCH's body reaches ``handle`` as sent, so its signature checks and it applies."""
    path = f"{BASE}user/mobile_state/"
    body = canonical_body({"favorites": ["7", 8]})
    headers = signed(state, "attendee", "PATCH", path, body)
    reply = served.patch(path, content=body, headers=headers)
    assert (reply.status_code, reply.json()) == (200, {"favorites": ["7", "8"]})
    assert account(state, "attendee").favorites == ["7", "8"]


def test_the_raw_query_is_signed_as_sent(
    state: MockState, served: httpx.Client
) -> None:
    """The request target reaches ``handle`` undecoded, so an encoded query still signs."""
    path = f"{BASE}mask_violations/capture/?attendee_access_code=MOCK%30001"
    reply = served.get(path, headers=signed(state, "coc", "GET", path))
    assert reply.status_code == 200  # signed over "%30", read as "MOCK0001"
    assert reply.json()["data"]["full_name"] == "Ada Example"


def test_authenticate_and_the_401_envelope(served: httpx.Client) -> None:
    """Sign-in answers the account's credentials; an unsigned call gets the 401 envelope."""
    body = canonical_body({"email": "sponsor@example.com", "password": "mock-sponsor"})
    reply = served.post(f"{BASE}authenticate/", content=body)
    assert reply.status_code == 200
    assert reply.json()["key"] == "mock-key-sponsor"
    refused = served.get(f"{BASE}user/check_features/")
    assert refused.status_code == 401
    assert refused.json() == {"code": 401, "error": "Unknown API key."}


def test_the_reply_has_one_date_the_mocks(served: httpx.Client) -> None:
    """The only ``Date`` header is ``handle``'s, from the mock's clock (D-53)."""
    reply = served.get(f"{BASE}nowhere/")
    assert reply.status_code == 404
    assert reply.headers.get_list("Date") == [formatdate(NOW, usegmt=True)]
    assert reply.headers["Content-Type"] == "application/json"


def test_a_malformed_length_is_refused_before_handle(served: httpx.Client) -> None:
    """A ``Content-Length`` that is not plain digits is 400, and no endpoint runs."""
    status = raw_request(
        served,
        f"PATCH {BASE}user/mobile_state/ HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        "Content-Length: +2\r\n\r\n{}",
    )
    assert status == b"400"


def test_the_log_names_the_call_but_no_query_body_or_secret(
    state: MockState, served: httpx.Client, capfd: pytest.CaptureFixture[str]
) -> None:
    """Each call logs its method, path and status, and never its query or body."""
    body = canonical_body({"email": "staff@example.com", "password": "mock-staff"})
    served.post(f"{BASE}authenticate/", content=body)
    path = f"{BASE}lead_retrieval/capture/?attendee_access_code=MOCK0001"
    served.get(path, headers=signed(state, "staff", "GET", path))
    log = capfd.readouterr().err
    assert f"POST {BASE}authenticate/ 200" in log
    assert f"GET {BASE}lead_retrieval/capture/ 400" in log  # staff names no sponsor
    for secret in ("mock-staff", "MOCK0001", "mock-key-staff", "mock-secret-staff"):
        assert secret not in log


def test_a_lead_note_logs_one_line_without_the_access_code(
    state: MockState, served: httpx.Client, capfd: pytest.CaptureFixture[str]
) -> None:
    """The code in ``lead_retrieval/<code>/note/`` is logged as ``<code>``, once."""
    capfd.readouterr()
    path = f"{BASE}lead_retrieval/MOCK0001/note/"
    body = canonical_body({"note": "met at the booth"})
    served.post(
        path, content=body, headers=signed(state, "sponsor", "POST", path, body)
    )
    [line] = log_lines(capfd)
    assert f"POST {BASE}lead_retrieval/<code>/note/ " in line
    assert "MOCK0001" not in line


def test_a_malformed_length_logs_one_line_without_the_query(
    served: httpx.Client, capfd: pytest.CaptureFixture[str]
) -> None:
    """The server's own 400 logs one sanitised line, not the request line or a message."""
    capfd.readouterr()
    status = raw_request(
        served,
        f"POST {BASE}mask_violations/capture/?attendee_access_code=MOCK0001 HTTP/1.1"
        "\r\nHost: 127.0.0.1\r\nContent-Length: +2\r\n\r\n{}",
    )
    assert status == b"400"
    [line] = log_lines(capfd)
    assert line.endswith(f"POST {BASE}mask_violations/capture/ 400")


def test_an_unsupported_method_logs_one_line_without_the_query(
    served: httpx.Client, capfd: pytest.CaptureFixture[str]
) -> None:
    """The server's own 501 for an unknown method logs one sanitised line."""
    capfd.readouterr()
    status = raw_request(
        served,
        f"OPTIONS {BASE}mask_violations/capture/?attendee_access_code=MOCK0001 "
        "HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
    )
    assert status == b"501"
    [line] = log_lines(capfd)
    assert line.endswith(f"OPTIONS {BASE}mask_violations/capture/ 501")


def test_the_banner_gives_every_device_its_url_and_every_account() -> None:
    """On 0.0.0.0 it lists localhost, the emulator's alias and each LAN address."""
    state = state_at()
    text = banner("0.0.0.0", 8000, state, ["192.168.1.20"])
    for url in (
        "http://localhost:8000",
        "http://10.0.2.2:8000",
        "http://192.168.1.20:8000",
    ):
        assert url in text
    for who in state.accounts:
        assert who.email in text and who.password in text
        assert who.key not in text and who.secret not in text


def test_the_banner_on_loopback_says_phones_cannot_reach_it() -> None:
    """Bound to 127.0.0.1, it offers no LAN URL and says how to serve phones."""
    text = banner("127.0.0.1", 8000, state_at(), ["192.168.1.20"])
    assert "192.168.1.20" not in text
    assert "use --host 0.0.0.0" in text
