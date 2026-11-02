"""What the staff pickers' tests share: a transport that goes offline, typing a search, Back.

Used by ``tests/test_lead_sponsor_picker.py`` and ``tests/test_staff_door.py``, whose
pages run over the mock's own transport (``tools/mock_api/transport.py``), and by the
tests of a tool's read on the way back from its picker (``going()``).
"""

from collections.abc import Awaitable, Callable

import flet as ft
import httpx
import pytest

from pycon_us.account import Account
from tests.harness import Shown

type Go = Callable[[Shown, Account, str], Awaitable[None]]


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


def going(monkeypatch: pytest.MonkeyPatch, start: str) -> Go:
    """Return a function that changes the location and the route, from ``start``.

    A change of the account stands for the render the Router makes on a location
    change.
    """
    location = [start]
    monkeypatch.setattr(ft, "use_route_location", lambda: location[0])

    async def to(shown: Shown, account: Account, where: str) -> None:
        """Move to ``where`` and let the render and its effects run."""
        location[0] = shown.session.page.route = where
        account.nickname = where
        await shown.settle()

    return to
