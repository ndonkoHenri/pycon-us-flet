"""I/O at explicit boundaries: storage, the feed fetch, logging and errors.

Each service is a small module with one job (docs/architecture.md). ``Services`` bundles
what a session uses, built once by ``App`` and reached through ``use_services()``. Later
phases add reminders, the API client, the sync worker and the scanner.
"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft

from pycon_us.config import YearData, load_year
from pycon_us.memory import ViewMemory
from pycon_us.services.storage import Storage, data_dir


def _set_event() -> asyncio.Event:
    """Return an ``asyncio.Event`` that is already set: a session starts in the foreground."""
    event = asyncio.Event()
    event.set()
    return event


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
        haptics: The platform's haptic feedback: the star's selection click (D-30).
        launcher: Opens web pages, apps, ``tel:`` and ``mailto:`` links, by the link
            rule in ``ui.links`` (INFO-14).
        clipboard: Copy for phone numbers and email addresses (``ui.links``).
        share: The platform's share sheet: the Developer screen's Share log (D-72).
        paths: The platform's storage paths: where the packaged app's ``console.log``
            is (F14).
        file_picker: The system's save dialog: Add to calendar's file on Android
            (``services.calendar``, D-272).
        closed: Set by ``close()`` when a new session has replaced this one (D-147).
        foreground: Set while the app is in the foreground: the lifecycle handler
            clears it on ``pause`` and sets it on ``resume``, and ``run_every()``
            loops wait for it, so nothing ticks in the background (D-40).
        shown_versions: The feed versions this session has logged D-112's content line
            for; ``AppScaffold``'s ``Shown`` logs each version once, from the first
            screen that shows it (D-165).
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
    file_picker: ft.FilePicker = field(default_factory=ft.FilePicker)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    foreground: asyncio.Event = field(default_factory=_set_event)
    shown_versions: set[int] = field(default_factory=set)

    @classmethod
    def create(cls, memory: ViewMemory) -> Services:
        """Build the session's services; call it while rendering, in the page's context.

        A Flet service registers with the page that is current when it is constructed.

        Args:
            memory: The process's one ``ViewMemory``, from ``main.py``.

        Returns:
            The services, with SharedPreferences and the data directory read afresh
            (D-108).

        Raises:
            YearDataError: The bundled year data is broken (a broken build).
            OSError: The data directory cannot be created (a broken install, D-120).
        """
        year = load_year()
        return cls(
            year=year,
            storage=Storage(ft.SharedPreferences(), data_dir(), year.conference.year),
            memory=memory,
            semantics=ft.SemanticsService(),
            haptics=ft.HapticFeedback(),
            launcher=ft.UrlLauncher(),
            clipboard=ft.Clipboard(),
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
