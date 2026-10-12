"""I/O at explicit boundaries: storage, the feed fetch, logging and errors.

Each service is a small module with one job (docs/architecture.md). ``Services`` bundles
what a session uses, built once by ``App`` and reached through ``use_services()``. Later
phases add reminders, the API client, the sync worker and the scanner.
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import flet as ft

from pycon_us.config import YearData, load_year
from pycon_us.services.storage import Storage, data_dir

if TYPE_CHECKING:  # state.py imports this package
    from pycon_us.state import ViewMemory


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
        closed: Set by ``close()`` when a new session has replaced this one (D-147).
        shown_versions: The feed versions this session has logged D-112's content line
            for; ``AppScaffold``'s ``Shown`` logs each version once, from the first
            screen that shows it (D-165).
    """

    year: YearData
    storage: Storage
    memory: ViewMemory
    semantics: ft.SemanticsService
    closed: asyncio.Event = field(default_factory=asyncio.Event)
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
        )

    def close(self) -> None:
        """Mark the session as replaced, so its long-running work stops (D-147).

        Flet closes a replaced session without unmounting it (F30): its effects keep
        running, and a store write from one fails. ``page.on_close`` calls this, and only
        it: a screen's own cleanup still stops just its own effect. Every long-running
        loop, and a feed refresh before it writes, checks ``closed``. Until U24 (D-149).
        """
        self.closed.set()


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
