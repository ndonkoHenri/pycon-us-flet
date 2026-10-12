"""The small labels sessions carry (decisions §M): so far ``TrackBadge`` (THEME-08, SCHED-20).

A badge is a text pill: a tonal fill per track in light and dark, or an outline for
"Registration required" (D-25; ux.md §3.4). Badges always carry text, so colour is never
the only signal (D-33), and every name comes from ``ConferenceInfo.track_name()``
(DATA-28). The colours are the current scheme's ``Tokens`` (D-24); the builders take
them as an argument, so a memoised row (D-153) that receives the tokens as a prop
(D-150) still draws the scheme on screen. #81 adds ``FavoriteButton`` here.
"""

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.models import Session
from pycon_us.theme import BadgeColors, Tokens

SPANISH = "En Español"
"""The label of a session given in Spanish (DATA-10)."""

REGISTRATION = "Registration required"
"""The label of a session that needs registration (DATA-09), as on session detail."""


def TrackBadge(label: str, colors: BadgeColors) -> ft.Control:
    """Return one badge: its label in a pill (ux.md §3.9).

    Not a ``Chip``: chips are interactive, and a badge is text. The label uses the
    Material 3 label type (``LABEL_SMALL``) and wraps inside the pill rather than
    clipping when a large text size makes it wider than the row (D-26).

    Args:
        label: What the badge says, in sentence case.
        colors: Its colours in the current scheme, from ``Tokens``.
    """
    return ft.Container(
        content=ft.Text(
            label,
            theme_style=ft.TextThemeStyle.LABEL_SMALL,
            color=colors.text,
            text_align=ft.TextAlign.CENTER,  # for a label that wraps at large text
        ),
        bgcolor=colors.fill,
        # Every badge has a 1 dp border, its fill's colour on a tonal one, so an
        # outlined badge is exactly as large as the tonal ones beside it.
        border=ft.Border.all(1, colors.fill or colors.text),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
    )


def session_badges(
    session: Session, info: ConferenceInfo, tokens: Tokens
) -> list[ft.Control]:
    """Return a session's badges: its track, then En Español, then Registration required.

    Ionic's order and set (SCHED-03): every session shows its track, so a charla shows
    both "Charla" and "En Español".

    Args:
        session: The session.
        info: The year's facts, for the track's display name (DATA-28).
        tokens: The current scheme's tokens.

    Returns:
        The badges; none for a session without a track and without either flag.
    """
    badges: list[ft.Control] = []
    key = session.track
    if key:  # a feed record without a kind has no track: no empty pill
        badges.append(TrackBadge(info.track_name(key), tokens.track_badge(key)))
    if session.spanish:
        badges.append(TrackBadge(SPANISH, tokens.spanish))
    if session.pre_registered:
        badges.append(TrackBadge(REGISTRATION, tokens.registration))
    return badges


def badge_row(badges: list[ft.Control]) -> ft.Row:
    """Return badges side by side, wrapping onto more lines when they don't fit.

    The gaps are on the 4 dp grid (ux.md §3.6): 8 dp between badges, as within a
    group, and 4 dp between wrapped lines, so a wrapped row stays compact.

    Args:
        badges: The badges, e.g. from ``session_badges()``.
    """
    return ft.Row(badges, wrap=True, spacing=8, run_spacing=4)
