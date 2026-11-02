"""F8's listener cut refuses connections while preserving the server's captures."""

import httpx
import pytest

from tools.mock_api.state import Lead
from tools.offline_scans import Listener

pytestmark = pytest.mark.loopback


def test_cut_and_restore_preserves_captures() -> None:
    """A closed listener cannot accept a scan; reopening keeps non-idempotent state."""
    listener = Listener(0)
    state = listener.state
    state.leads.append(Lead(1, "MOCK0001", state.now()))
    url = f"http://127.0.0.1:{listener.port}/"
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            assert client.get(url).status_code == 404
            listener.offline()
            with pytest.raises(httpx.ConnectError):
                client.get(url)
            listener.online()
            assert client.get(url).status_code == 404
            assert listener.state is state
            assert state.capture == "non_idempotent"
            assert [(lead.sponsor_id, lead.access_code) for lead in state.leads] == [
                (1, "MOCK0001")
            ]
    finally:
        listener.offline()
