"""I/O at explicit boundaries: storage, the feed fetch, logging and errors.

Each service is a small module with one job (docs/architecture.md). ``Services`` bundles
what a session uses, built once by ``App`` and reached through ``use_services()``. Later
phases add the scanner.
"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import flet as ft

from pycon_us import capabilities
from pycon_us.config import YearData, load_year
from pycon_us.memory import ViewMemory
from pycon_us.services.api import ApiClient, Credentials
from pycon_us.services.credentials import CredentialStorage, secure_storage
from pycon_us.services.data_files import data_dir
from pycon_us.services.favorites_sync import FavoritesSync
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.presence import Presence
from pycon_us.services.private_api import PrivateApi, signed_out
from pycon_us.services.reminders import Scheduler
from pycon_us.services.reminders import start as start_reminders
from pycon_us.services.storage import Storage

if TYPE_CHECKING:  # imported only when the build has it (D-63)
    from flet_permission_handler import PermissionHandler


def _set_event() -> asyncio.Event:
    """Return an ``asyncio.Event`` that is already set: a session starts in the foreground."""
    event = asyncio.Event()
    event.set()
    return event


def kick_on_reconnect(
    wake: asyncio.Event,
) -> Callable[[ft.ConnectivityChangeEvent], None]:
    """Return the ``Connectivity`` handler that wakes the sync loop on a reconnection.

    Any connection but ``NONE`` sets ``wake``: the worker trusts its transport errors,
    so a connection that reaches nothing only costs one pass (D-56, D-407).
    """

    def on_change(e: ft.ConnectivityChangeEvent) -> None:
        if any(kind is not ft.ConnectivityType.NONE for kind in e.connectivity):
            wake.set()

    return on_change


def _permissions() -> PermissionHandler | None:
    """Return a ``PermissionHandler`` when the build has the extension, else ``None``.

    The extension is imported only then, so the companion app is never sent a control
    its client may lack (D-63, F14).
    """
    if not capabilities.PERMISSIONS:
        return None
    from flet_permission_handler import PermissionHandler

    return PermissionHandler()


@dataclass(frozen=True, eq=False)
class Services:
    """What one session uses to reach the year's data, storage and the platform.

    Built once per session by ``Services.create()`` in ``App``'s first render (architecture
    §4.2); screens get it from ``use_services()`` and never build a Flet service
    themselves. P1 and later add the Flet services their screens need.

    Attributes:
        year: The active year's bundled data (``config.load_year()``).
        storage: SharedPreferences and the durable data directory, for that year.
        memory: The process's one ``ViewMemory`` (D-143).
        semantics: The platform's accessibility services; ``App`` reads the OS flags
            through it (F13).
        haptics: The platform's haptic feedback: the star's selection click (D-30)
            and the scan screen's outcomes (ux.md §7.2).
        launcher: Opens web pages, apps, ``tel:`` and ``mailto:`` links, by the link
            rule in ``ui.links`` (INFO-14).
        clipboard: Copy for phone numbers and email addresses (``ui.links``).
        share: The platform's share sheet: the Developer screen's Share log (D-72).
        paths: The platform's storage paths: where the packaged app's ``console.log``
            is (F14).
        wakelock: Keeps the screen on while the scan screen is open (D-65, #724).
        file_picker: The system's save dialog: Add to calendar's file on Android
            (``services.calendar``, D-272).
        permissions: ``flet-permission-handler``'s service: permission status, the
            app's settings page and the camera (D-61). ``None`` unless the build has it
            (``capabilities.PERMISSIONS``), so always ``None`` in the companion app.
        reminders: E3's ``Scheduler``, which schedules the reminder plan (D-389).
            ``None`` unless the build has E3 (``capabilities.REMINDERS``), so always
            ``None`` in the companion app, which keeps the interim (D-60).
        closed: Set by ``close()`` when a new session has replaced this one (D-147).
        foreground: Set while the app is in the foreground: the lifecycle handler
            clears it on ``pause`` and sets it on ``resume``, and ``run_every()``
            loops wait for it, so nothing ticks in the background (D-40).
        background: Its opposite, set from ``pause`` to ``resume``, for work that
            stops on the way out: the scan screen lets go of the wake lock (#724).
        presence: Whether the app's window is in front, from ``inactive`` to
            ``resume``: ``ui.focus_back`` waits on it for the return from another
            app's window (D-372).
        shown_versions: The feed versions this session has logged D-112's content line
            for; ``AppScaffold``'s ``Shown`` logs each version once, from the first
            screen that shows it (D-165).
        private_api: Holds ``api``, rebuilt when Developer's mock API URL changes
            (``services.private_api``, D-51).
        credentials: Where the mock account's key and secret are kept: the keystore
            when the build has ``flet-secure-storage``, else memory for the session
            (``services.credentials``, D-49, D-63).
        outbox: The staff outbox's database (``services.outbox_db``, D-49), which
            opens ``outbox.db`` on first use: only the staff tools use it, and D-51
            hides them without a mock API URL. ``None`` in tests that don't need it.
        favorites_sync: Keeps the favourites in step with the mock account while
            signed in (``services.favorites_sync``, D-406); ``App`` runs it.
        sync_wake: Set to ask the staff sync loop for a pass now (``kick_sync()``):
            an enqueue, "Sync now", a resume and a reconnection (D-56).
        connectivity: The platform's connectivity: a change to anything but
            ``NONE`` sets ``sync_wake`` (``kick_on_reconnect()``).
    """

    year: YearData
    storage: Storage
    memory: ViewMemory
    semantics: ft.SemanticsService
    haptics: ft.HapticFeedback
    launcher: ft.UrlLauncher
    clipboard: ft.Clipboard
    # Defaults, unlike the services above, since only a few screens use them: the
    # factories run inside `create()`, in the page's context, so they register with
    # the page like the rest.
    share: ft.Share = field(default_factory=ft.Share)
    paths: ft.StoragePaths = field(default_factory=ft.StoragePaths)
    wakelock: ft.Wakelock = field(default_factory=ft.Wakelock)
    file_picker: ft.FilePicker = field(default_factory=ft.FilePicker)
    permissions: PermissionHandler | None = field(default_factory=_permissions)
    reminders: Scheduler | None = None
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    foreground: asyncio.Event = field(default_factory=_set_event)
    background: asyncio.Event = field(default_factory=asyncio.Event)
    presence: Presence = field(default_factory=Presence)
    shown_versions: set[int] = field(default_factory=set)
    private_api: PrivateApi = field(default_factory=PrivateApi)
    credentials: CredentialStorage = field(
        default_factory=lambda: CredentialStorage(secure=None)
    )
    outbox: OutboxDb | None = None
    favorites_sync: FavoritesSync = field(default_factory=FavoritesSync)
    sync_wake: asyncio.Event = field(default_factory=asyncio.Event)
    connectivity: ft.Connectivity | None = None

    @property
    def api(self) -> ApiClient | None:
        """The private-API client: None unless a mock API URL is set (D-51)."""
        return self.private_api.client

    @classmethod
    def create(
        cls, memory: ViewMemory, credentials: Credentials = signed_out
    ) -> Services:
        """Build the session's services; call it while rendering, in the page's context.

        A Flet service registers with the page that is current when it is constructed.

        Args:
            memory: The process's one ``ViewMemory``, from ``main.py``.
            credentials: What the private-API client signs with: the ``Account``
                store's ``credentials`` (#684).

        Returns:
            The services, with SharedPreferences and the data directory read afresh
            (D-108).

        Raises:
            YearDataError: The bundled year data is broken (a broken build).
            OSError: The data directory cannot be created (a broken install, D-120).
        """
        year = load_year()
        permissions = _permissions()
        directory = data_dir()
        sync_wake = asyncio.Event()
        return cls(
            year=year,
            storage=Storage(ft.SharedPreferences(), directory, year.conference.year),
            memory=memory,
            semantics=ft.SemanticsService(),
            haptics=ft.HapticFeedback(),
            launcher=ft.UrlLauncher(),
            clipboard=ft.Clipboard(),
            permissions=permissions,
            reminders=start_reminders(permissions),
            private_api=PrivateApi(credentials=credentials),
            credentials=CredentialStorage(secure_storage()),
            outbox=OutboxDb(directory),
            sync_wake=sync_wake,
            # The handler at construction: one set later would need an update (F257).
            connectivity=ft.Connectivity(on_change=kick_on_reconnect(sync_wake)),
        )

    def close(self) -> None:
        """Mark the session as replaced, so its long-running work stops (D-147).

        Flet closes a replaced session without unmounting it (F30): its effects keep
        running, and a store write from one fails. ``page.on_close`` calls this, and only
        it: a screen's own cleanup still stops just its own effect. Every long-running
        loop, and a feed refresh before it writes, checks ``closed``. Until U24 (D-149).
        """
        self.closed.set()
        # Wakes the run_every() loops that wait for a resume, so they see `closed` and
        # return: a session replaced in the background never resumes.
        self.foreground.set()
        self.background.set()  # and the scan screen's wake lock, which lets go
        self.presence.close()  # and a focus that waits for a return (D-372)
        self.sync_wake.set()  # and the staff sync loop's wait (services.sync)
        if self.reminders is not None:  # and the reminders' loop, which then returns
            self.reminders.request()
        self.favorites_sync.request()  # and the favourites sync's, which returns too
        if self.outbox is not None:  # a late write is refused, not raised (D-120)
            self.outbox.close()

    def kick_sync(self) -> None:
        """Ask the staff sync loop for a pass now; without one, the next one starts so."""
        self.sync_wake.set()

    async def run_every(self, seconds: float, action: Callable[[], object]) -> None:
        """Call ``action`` now, then every ``seconds`` while the app is in the foreground.

        In the background it waits without doing anything, and calls ``action`` as soon
        as the app resumes when a call fell due meanwhile, so a screen catches up at
        once (D-40). It returns when the session closes (D-147); an effect's cleanup
        stops it sooner by cancelling its task.

        Args:
            seconds: The time between two calls.
            action: What to do; it runs on the event loop, so it may write stores.
        """
        while True:
            await self.foreground.wait()
            if self.closed.is_set():
                return
            action()
            # Sleeps `seconds`, or less when the session closes meanwhile.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.closed.wait(), seconds)


ServicesCtx: ft.ContextProvider[Services | None] = ft.create_context(None)
"""Provides the session's ``Services``; ``App`` writes the provider out (D-69)."""


def use_services() -> Services:
    """Return the session's ``Services``; a plain value, so it subscribes to nothing.

    Raises:
        RuntimeError: No ``ServicesCtx`` provider is above the calling component.
    """
    services = ft.use_context(ServicesCtx)
    if services is None:
        raise RuntimeError("use_services() needs a ServicesCtx provider above it")
    return services
