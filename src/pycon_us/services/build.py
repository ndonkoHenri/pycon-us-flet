"""Which build of the app runs: its version and, in a packaged build, its number (D-386).

``flet build --build-number N`` reaches only the native side (Android's ``versionCode``,
iOS's ``CFBundleVersion``), so Python asks Flutter for it: ``page.get_package_info()``
(U4, landed at the pin ``08b89cce5``). Outside a packaged build that call describes the
Flet client running the app (the companion app's own version), so the app asks it only
when ``is_embedded()`` and otherwise says ``pycon_us.__version__`` alone (D-83). About
this app's Version row and the diagnostics text both say it.
"""

import logging
from dataclasses import dataclass

import flet as ft
from flet.utils import is_embedded

from pycon_us import __version__
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Build:
    """The running build: its version and its build number.

    Attributes:
        version: The version users see, e.g. ``0.4.0``.
        number: The build number, e.g. ``812``; None outside a packaged build, or
            when the platform did not say.
    """

    version: str
    number: str | None = None

    @property
    def label(self) -> str:
        """The version as the Version row says it: ``0.4.0 (812)``, or ``0.4.0``."""
        return f"{self.version} ({self.number})" if self.number else self.version


UNPACKAGED = Build(__version__)
"""What the app says before, or without, the platform's answer: ``__version__`` alone."""

_packaged: Build | None = None
"""A packaged build's answer, read once: it cannot change while the process runs."""


def known_build() -> Build:
    """Return the build as far as it is known without asking: the answer once read."""
    return _packaged or UNPACKAGED


async def read_build(page: ft.Page) -> Build:
    """Return the running build, asking the platform once in a packaged build.

    Call it from an ``async`` handler or effect (D-70).

    Args:
        page: The session's page.

    Returns:
        ``UNPACKAGED`` outside a packaged build, and when the call fails (logged by
        class, D-72); else the packaged app's version and build number.
    """
    global _packaged
    if not is_embedded():
        return UNPACKAGED
    if _packaged is None:
        try:
            info = await page.get_package_info()
        except SERVICE_ERRORS as error:
            logger.warning("Could not read the package info: %s", type(error).__name__)
            return UNPACKAGED
        _packaged = Build(info.version or __version__, info.build_number or None)
    return _packaged


def use_build() -> Build:
    """Return the running build, as a hook: what is known now, then the platform's answer.

    The first About this app of a packaged run says the version alone until the answer
    arrives; every later one starts with the answer (``known_build()``).
    """
    build, set_build = ft.use_state(known_build)

    async def read() -> None:
        set_build(await read_build(ft.context.page))

    ft.use_effect(read, [])
    return build
