"""PyCon US conference companion, built with Python and Flet.

The import package of the app. ``src/main.py`` is the entry point; the modules
are laid out in ``docs/decisions.md`` section M.
"""

__version__ = "0.1.0"

APP_NAME = "Conf Companion"
"""The display name: a neutral placeholder until O-4 (D-36), equal to ``[tool.flet] product``."""

CALENDAR_DOMAIN = "conf-companion.invalid"
"""What follows ``@`` in a calendar event's ``UID`` (``core/ics.py``, D-268).

A placeholder until O-4 (D-36) names the app; ``.invalid`` is reserved (RFC 2606), so it
is no one's domain. Once a build leaves our devices it never changes again: a new domain
makes every event a user exports again a second copy in their calendar.
"""

FLET_VERSION = "source build"
"""The Flet version About this app and the diagnostics text name while the app builds from
the pinned source checkout (D-81): a packaged app reports ``0.1.0`` then, the host the
nearest tag (development.md §2.2). The PR that pins ``flet==1.1.0`` uses
``flet.version.flet_version`` instead (D-271)."""
