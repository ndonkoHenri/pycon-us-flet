"""A session's badges: the pills that say its track and its flags.

A badge is a text pill: a tonal fill per track in light and dark, or an outline for
"Registration required" and "Changed" (D-25, D-315; ux.md §3.4); in high contrast every badge is outlined,
1.5 dp wide (THEME-06). Badges always carry text, so colour is never the only signal
(D-33), and every name comes from `ConferenceInfo.track_name()` (DATA-28). The
colours are the current scheme's `Tokens` (D-24); the builders take them as an
argument, so a memoised row (D-153) that receives the tokens as a prop (D-150) still
draws the scheme on screen.

The star beside them, and the SnackBars of a favourites edit, are `ui/favorite.py`'s
(D-267).
"""

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.models import Session
from pycon_us.theme import Tokens
from pycon_us.theme_badges import BadgeColors

SPANISH = "En Español"
"""The label of a session given in Spanish (DATA-10)."""

REGISTRATION = "Registration required"
"""The label of a session that needs registration (DATA-09), as on session detail."""

NEW_TRACK = "New track"
"""The badge of a track new this year (SCHED-21), shown beside the track's own badge
on the Tracks hub and the track's page, outlined in `Tokens.new_track` (D-199)."""


CHANGED = "Changed"
"""The badge of a session whose time, room or title changed in the last 24 h (NEW-04),
outlined in `Tokens.changed` (D-315); its row says what changed (`changed_phrase()`)."""


def TrackBadge(label: str, colors: BadgeColors) -> ft.Control:
    """Return one badge: its label in a pill (ux.md §3.9).

    Not a `Chip`: chips are interactive, and a badge is text. The label uses the
    Material 3 label type (`LABEL_SMALL`) and wraps inside the pill rather than
    clipping when a large text size makes it wider than the row (D-26). Its lines
    start at the pill's start edge, as the text around it does: a one-line label fills
    the pill, so the alignment shows only once it wraps (#579).

    Args:
        label: What the badge says, in sentence case.
        colors: Its colours in the current scheme, from `Tokens`.
    """
    return ft.Container(
        content=ft.Text(
            label,
            theme_style=ft.TextThemeStyle.LABEL_SMALL,
            color=colors.text,
            text_align=ft.TextAlign.START,
        ),
        bgcolor=colors.fill,
        # Every badge has a border, its fill's colour on a tonal one, so an outlined
        # badge is exactly as large as the tonal ones beside it: 1 dp, or 1.5 dp for
        # every badge in high contrast (THEME-06).
        border=ft.Border.all(colors.border_width, colors.fill or colors.text),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
    )


def badge_specs(
    session: Session,
    info: ConferenceInfo,
    tokens: Tokens,
    *,
    omit: frozenset[str] = frozenset(),
    changed: bool = False,
) -> list[tuple[str, BadgeColors]]:
    """Return a session's badges as labels and colours, in the one order they show in.

    Its track, then En Español, then Registration required: Ionic's order and set
    (SCHED-03), so a charla shows both "Charla" and "En Español"; then Changed, a
    status of the last 24 h rather than of the session (D-315). A row draws them with
    `TrackBadge` and also says their labels (D-33).

    Args:
        session: The session.
        info: The year's facts, for the track's display name (DATA-28).
        tokens: The current scheme's tokens.
        omit: Labels the page already shows, left out of every row: a track page's
            own badge, and "En Español" on the Charlas page (D-199).
        changed: Whether its time, room or title changed in the last 24 h
            (`ChangeLog.recent()`).

    Returns:
        The label and colours of each badge; none for a session without a track and
        without either flag, or whose badges are all omitted.
    """
    specs: list[tuple[str, BadgeColors]] = []
    key = session.track
    if key:  # a feed record without a kind has no track: no empty pill
        specs.append((info.track_name(key), tokens.track_badge(key)))
    if session.spanish:
        specs.append((SPANISH, tokens.spanish))
    if session.pre_registered:
        specs.append((REGISTRATION, tokens.registration))
    if changed:
        specs.append((CHANGED, tokens.changed))
    return [spec for spec in specs if spec[0] not in omit]


def badge_row(badges: list[ft.Control]) -> ft.Row:
    """Return badges side by side, wrapping onto more lines when they don't fit.

    The gaps are on the 4 dp grid (ux.md §3.6): 8 dp between badges, as within a
    group, and 4 dp between wrapped lines, so a wrapped row stays compact.

    Args:
        badges: The badges, e.g. `TrackBadge`s.
    """
    return ft.Row(badges, wrap=True, spacing=8, run_spacing=4)


def ChangedBadge(
    text: str, said: str, colors: BadgeColors, identifier: str
) -> ft.Control:
    """Return session detail's badge of one recent change, read as one phrase.

    Drawn as the rows' Changed badge (D-315), it shows the old value, "Was Fri, May 15,
    10:30 AM", and a screen reader hears it whole, "Was Friday, May 15, 10:30 AM"
    (ux.md §5.5, D-33).

    Args:
        text: What it shows (`change_views.detail_badge()`).
        said: What a screen reader says.
        colors: `Tokens.changed`.
        identifier: Its semantics identifier, e.g. `session.changed.room`.
    """
    return ft.Semantics(
        label=said,
        identifier=identifier,
        container=True,
        exclude_semantics=True,  # the label replaces the shown text, not repeated
        content=TrackBadge(text, colors),
    )
