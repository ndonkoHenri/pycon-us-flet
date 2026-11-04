"""PyCon US conference companion, built with Python and Flet.

The import package of the app. `src/main.py` is the entry point; each module's
docstring says what it is for, and `docs/decisions.md` section M holds the
names.
"""

__version__ = "0.4.0"

APP_NAME = "Conf Companion"
"""The display name, neutral and with no PSF mark (D-36, D-452), equal to `[tool.flet] product`."""

CALENDAR_DOMAIN = "confcompanion.ndonkohenri.github.io"
"""What follows `@` in a calendar event's `UID` (`core/ics.py`, D-268, D-452).

Only an identifier: nothing is ever fetched from it. Once a build leaves our devices it
never changes again: a new domain makes every event a user exports again a second copy
in their calendar.
"""

SOURCE_URL: str | None = None
"""The app's source repository, or None while it is private (D-88, D-292).

About this app shows a Source code row and every screen's overflow has View source
(D-461) only when it is set: a link to a private repository would open a 404 for
everyone outside the team. The PR that makes the repository public (P4) sets it to
the repository's `https` address.
"""

FLET_VERSION = "source build"
"""The Flet version About this app and the diagnostics text name while the app builds from
the pinned source checkout (D-81): a packaged app reports `0.1.0` then, the host the
nearest tag (development.md §2.2). The PR that pins `flet==1.1.0` uses
`flet.version.flet_version` instead (D-271)."""
