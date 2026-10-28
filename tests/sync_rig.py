"""The sync worker's rig: a real ``Account`` signed in to the in-process mock (#692).

``Rig`` holds what ``SyncWorker`` works with: the outbox in a temporary directory, the
``Account`` and ``Staff`` stores, an ``ApiClient`` that signs with the account's key over
``tools/mock_api/transport.py`` (so the mock checks every signature and counts every
write), and one clock the mock, the client and the worker share. ``Wire`` records each
request and lets a test hold one or act right after it.
"""

from collections.abc import Awaitable, Callable
from functools import partial

import httpx

from pycon_us.account import Account, SignIn
from pycon_us.core import outbox
from pycon_us.core.outbox import Row, Status
from pycon_us.services.api import ApiClient
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import Storage
from pycon_us.services.sync import SyncWorker
from pycon_us.staff import Staff
from tests.api_clients import BASE_URL, Recorder
from tests.mock_calls import Clock, state_at
from tools.mock_api.state import Capture
from tools.mock_api.transport import mock_transport

SENDS = ("lead_retrieval/", "check_in/")
"""The paths of the outbox's sends, so sign-ins are left out of what was sent."""


class Wire(Recorder):
    """A recorded transport a test can hold, or act on right after a reply.

    Attributes:
        gate: While set to an unset event, each request waits for it once recorded.
        then: Awaited once, right after the next reply, then dropped.
        before: Called with each request before the mock sees it, e.g. to arm a fault.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Record every request to ``inner``, holding none."""
        super().__init__(inner)
        self.gate: Awaitable[object] | None = None
        self.then: Callable[[], Awaitable[object]] | None = None
        self.before: Callable[[httpx.Request], None] | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request, wait at the gate, answer it, then run ``then``."""
        self.sent.append(request)
        if self.before is not None:
            self.before(request)
        if self.gate is not None:
            await self.gate
        response = await self.inner.handle_async_request(request)
        if self.then is not None:
            then, self.then = self.then, None
            await then()
        return response


class Rig:
    """A signed-in session's outbox, stores and client, over the seeded mock.

    Attributes:
        db: The outbox.
        clock: The time for the mock, the client's signatures and the worker.
        state: The mock's state: what it recorded.
        wire: Every request sent, sign-ins included.
        account: The ``Account`` store, signed in by ``sign_in()``.
        staff: The ``Staff`` store the worker reports to.
        api: The client, signing with the account's key.
        refused: How often the worker said the key was refused.
    """

    def __init__(
        self,
        db: OutboxDb,
        storage: Storage,
        credentials: CredentialStorage,
        capture: Capture = "idempotent",
    ) -> None:
        """Build the rig signed out, at the mock's fixed start time."""
        self.db = db
        self._storage = storage
        self._credentials = credentials
        self.clock = Clock()
        self.state = state_at(capture, self.clock)
        self.wire = Wire(mock_transport(self.state))
        self.account = Account()
        self.staff = Staff()
        self.api = ApiClient(
            BASE_URL,
            2026,
            self.account.credentials,
            transport=self.wire,
            now=self.clock,
        )
        self.refused = 0

    async def sign_in(self, role: str) -> None:
        """Sign the account in as the seeded ``role``, through ``authenticate``."""
        outcome = await self.account.sign_in(
            self.api,
            self._storage,
            self._credentials,
            f"{role}@example.com",
            f"mock-{role}",
        )
        assert outcome is SignIn.SIGNED_IN

    async def sign_out(self) -> None:
        """Sign the account out, as Account › Sign out does."""
        await self.account.sign_out(self._storage, self._credentials)

    def worker(self) -> SyncWorker:
        """A worker for this rig's client, counting refusals in ``refused``."""

        def refused() -> None:
            self.refused += 1

        return SyncWorker(
            self.db,
            self.api,
            self.account,
            self.staff,
            on_refused=refused,
            now=self.clock,
        )

    def lead(
        self,
        code: str = "MOCK0001",
        validator: str = "v4l1d01",
        sponsor: str | None = None,
    ) -> None:
        """Queue the signed-in account's lead scan, for ``sponsor`` (None: its own)."""
        decide = partial(
            outbox.scan_lead,
            owner=self.account.owner,
            code=code,
            payload={"badge_validator": validator},
            sponsor_id=sponsor,
            sponsor_name=None if sponsor is None else f"Sponsor {sponsor}",
            now=self.clock(),
        )
        assert self.db.enqueue(code, decide) is not None

    def note(
        self, text: str, code: str = "MOCK0001", sponsor: str | None = None
    ) -> None:
        """Queue the signed-in account's note on ``code``'s lead."""
        decide = partial(
            outbox.save_note,
            owner=self.account.owner,
            code=code,
            note=text,
            sponsor_id=sponsor,
            sponsor_name=None,
            now=self.clock(),
        )
        assert self.db.enqueue(code, decide) is not None

    def door(self, code: str = "MOCK0001", product: int = 10) -> None:
        """Queue the signed-in account's check-in of ``code`` to ``product``."""
        payload = {
            "attendee_access_code": code,
            "badge_validator": "v4l1d01",
            "scanned_at": "2026-05-13T09:00:00.000Z",
            f"product-redeem-{product}": product,
            f"product-{product}-quantity": 1,
        }
        decide = partial(
            outbox.admit,
            owner=self.account.owner,
            code=code,
            product_ids=[product],
            session="door-1",
            payload=payload,
            sponsor_id=None,
            sponsor_name=None,
            now=self.clock(),
        )
        assert self.db.enqueue(code, decide) is not None

    def rows(self, owner: str | None = None) -> list[Row]:
        """Every row of ``owner`` (the signed-in account by default), oldest first."""
        found = self.db.rows(owner or self.account.owner, list(Status))
        assert found is not None
        return found

    def sends(self) -> list[tuple[str, str | None]]:
        """Each outbox send so far: its path under the year's API, and its key."""
        prefix = "/2026/api/v1/"
        return [
            (request.url.path.removeprefix(prefix), request.headers.get("X-API-Key"))
            for request in self.wire.sent
            if request.url.path.removeprefix(prefix).startswith(SENDS)
        ]
