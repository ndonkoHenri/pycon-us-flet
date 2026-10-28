"""What the staff pickers' tests share: a transport that goes offline, and typing a search.

Used by ``tests/test_lead_sponsor_picker.py`` and ``tests/test_staff_door.py``, whose
pages run over the mock's own transport (``tools/mock_api/transport.py``).
"""

import flet as ft
import httpx

from tests.harness import Shown


class Switch(httpx.AsyncBaseTransport):
    """The mock's transport, or no connection while ``offline`` is set."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Answer through ``inner``, online."""
        self.inner = inner
        self.offline = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Raise ``ConnectError`` offline, else let ``inner`` answer."""
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        return await self.inner.handle_async_request(request)


async def search(shown: Shown, text: str) -> None:
    """Type ``text`` in the page's one search field, as Flutter reports it."""
    (field,) = shown.find(ft.TextField)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
