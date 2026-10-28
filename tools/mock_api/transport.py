"""The mock API behind an ``httpx.MockTransport``, for client tests (D-50).

The request target and the body reach ``handle`` exactly as the client sent them, so
the signature is checked over the same bytes the client signed. Faults come later
(D-57).
"""

import httpx

from tools.mock_api.handlers import handle
from tools.mock_api.state import MockState


def mock_transport(state: MockState) -> httpx.MockTransport:
    """Route an ``httpx`` client's requests to the in-process mock.

    Args:
        state: The mock's state, shared by every request through this transport.

    Returns:
        A transport to pass to ``httpx.AsyncClient(transport=...)``.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        """Answer one request with ``handle``'s reply."""
        status, headers, body = handle(
            state,
            request.method,
            request.url.raw_path.decode("ascii"),
            request.headers,
            request.content,
        )
        return httpx.Response(status, headers=headers, content=body)

    return httpx.MockTransport(respond)
