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

SOURCE_URL: str | None = "https://github.com/ndonkoHenri/pycon-us-flet"
"""The app's source repository (D-88, D-292, D-505).

About this app shows a Source code row and every screen's overflow has View source
(D-461) only when it is set. A build must never ship it set while the repository is
private: the link would open a 404 for everyone outside the team.
"""
