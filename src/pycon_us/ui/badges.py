"""What a session carries besides its text (decisions §M): its badges and its star.

A badge is a text pill: a tonal fill per track in light and dark, or an outline for
"Registration required" (D-25; ux.md §3.4). Badges always carry text, so colour is never
the only signal (D-33), and every name comes from ``ConferenceInfo.track_name()``
(DATA-28). The colours are the current scheme's ``Tokens`` (D-24); the builders take
them as an argument, so a memoised row (D-153) that receives the tokens as a prop
(D-150) still draws the scheme on screen.

``FavoriteButton`` is the one favourite control (D-30): a 48 dp star on every session
row and in session detail. A list owner gets the one handler its stars share from
``use_favorite_toggle()``, which saves, gives the selection click and shows the
SnackBar of ux.md §4.4 (D-184). ``selection_click()`` is that click, which search's
scope chips give too (ux.md §4.5).
"""

import logging
from collections.abc import Awaitable, Callable

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.models import Session
from pycon_us.favorites import Change, Favorites
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS, Storage
from pycon_us.theme import BadgeColors, Tokens

logger = logging.getLogger(__name__)

SPANISH = "En Español"
"""The label of a session given in Spanish (DATA-10)."""

REGISTRATION = "Registration required"
"""The label of a session that needs registration (DATA-09), as on session detail."""

NEW_TRACK = "New track"
"""The badge of a track new this year (SCHED-21), shown beside the track's own badge
on the Tracks hub and the track's page, outlined in ``Tokens.new_track`` (D-197)."""

FAVORITE_LABEL = "Save to My schedule"
"""The star's name for screen readers, the same in both states: its toggle state says
whether the session is saved ("Save to My schedule, switch, on"; D-184)."""

ADD_LABEL = "Add to My schedule"
"""The star's tooltip while the session is not saved (D-30): what a tap does."""

REMOVE_LABEL = "Remove from My schedule"
"""The star's tooltip while the session is saved."""

REMOVED = "Removed from My schedule"
"""The SnackBar after a removal, with Undo (ux.md §4.4): the row may vanish."""

NOT_SAVED = "Couldn't save your change"
"""The SnackBar when an edit was shown but not written (D-120, D-172)."""

UNDO = "Undo"
"""The SnackBar's one action when the edit can be taken back (D-29)."""

SNACK_BAR_MS = 4000
"""How long a SnackBar shows (ux.md §4.5), unless a screen reader keeps it (D-184)."""

type ToggleFavorite = Callable[[str], Awaitable[None]]
"""A list's one star handler: ``await on_toggle(session_id)``."""


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


def badge_specs(
    session: Session,
    info: ConferenceInfo,
    tokens: Tokens,
    *,
    omit: frozenset[str] = frozenset(),
) -> list[tuple[str, BadgeColors]]:
    """Return a session's badges as labels and colours, in the one order they show in.

    Its track, then En Español, then Registration required: Ionic's order and set
    (SCHED-03), so a charla shows both "Charla" and "En Español". A row draws them
    with ``TrackBadge`` and also says their labels (D-33).

    Args:
        session: The session.
        info: The year's facts, for the track's display name (DATA-28).
        tokens: The current scheme's tokens.
        omit: Labels the page already shows, left out of every row: a track page's
            own badge, and "En Español" on the Charlas page (D-197).

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
    return [spec for spec in specs if spec[0] not in omit]


def session_badges(
    session: Session, info: ConferenceInfo, tokens: Tokens
) -> list[ft.Control]:
    """Return a session's badges drawn: ``badge_specs()`` as ``TrackBadge``s.

    Args:
        session: The session.
        info: The year's facts, for the track's display name (DATA-28).
        tokens: The current scheme's tokens.
    """
    specs = badge_specs(session, info, tokens)
    return [TrackBadge(label, colors) for label, colors in specs]


def badge_row(badges: list[ft.Control]) -> ft.Row:
    """Return badges side by side, wrapping onto more lines when they don't fit.

    The gaps are on the 4 dp grid (ux.md §3.6): 8 dp between badges, as within a
    group, and 4 dp between wrapped lines, so a wrapped row stays compact.

    Args:
        badges: The badges, e.g. from ``session_badges()``.
    """
    return ft.Row(badges, wrap=True, spacing=8, run_spacing=4)


def FavoriteButton(
    selected: bool,
    on_click: ft.ControlEventHandler[ft.IconButton],
    *,
    color: str,
    identifier: str | None = None,
) -> ft.Control:
    """Return the star (D-30): a 48 dp icon button, filled while the session is saved.

    A plain builder, as ``TrackBadge``: the memoised row that holds it (D-153) passes
    the scheme's ``Tokens.favorite`` as ``color``. Its tooltip says what a tap does,
    "Add to My schedule" or "Remove from My schedule" (D-27). A screen reader gets one
    node: the stable name ``FAVORITE_LABEL``, a switch, and the saved state as on or
    off (D-184). The ``IconButton`` alone came out nameless and stateless in
    TalkBack's tree (S2), since a tooltip is not an Android content description.

    The state is said once: the tooltip is left out of the semantics (iOS would read
    it after the label), and the icon is swapped here rather than through
    ``IconButton.selected``, which would add a "selected" to the toggle's "on".

    Args:
        selected: Whether the session is saved to My schedule.
        on_click: What a tap does; it calls the list owner's
            ``use_favorite_toggle()`` handler with the row's session.
        color: The filled star's colour, ``Tokens.favorite``.
        identifier: The node's semantics identifier for UI tests,
            ``<screen>.favorite.<session id>`` (decisions §M).
    """
    return ft.MergeSemantics(
        content=ft.Semantics(
            label=FAVORITE_LABEL,
            button=True,
            toggled=selected,
            identifier=identifier,
            content=ft.IconButton(
                # Outlined when off, filled when on (D-27).
                icon=ft.Icons.STAR if selected else ft.Icons.STAR_BORDER,
                icon_color=color if selected else None,
                tooltip=ft.Tooltip(
                    message=REMOVE_LABEL if selected else ADD_LABEL,
                    exclude_from_semantics=True,
                ),
                on_click=on_click,
            ),
        )
    )


def feedback(change: Change) -> str | None:
    """Return what the SnackBar says after a star tap, or None when it says nothing.

    An add says nothing: the filled star and the selection click are its feedback. A
    removal says so, because the row may vanish (My schedule). An edit that was shown
    but not saved says that instead, as the tap's one SnackBar (ux.md §4.4).

    Args:
        change: What ``Favorites.toggle()`` or ``Favorites.undo()`` returned.
    """
    if not change.saved:
        return NOT_SAVED
    if change.removed:
        return REMOVED
    return None


async def selection_click(haptics: ft.HapticFeedback) -> None:
    """Give the selection click (ux.md §4.5), logging rather than reporting a failure.

    Args:
        haptics: ``Services.haptics``.
    """
    try:
        await haptics.selection_click()
    except SERVICE_ERRORS:  # a missed click is not worth an error message
        logger.warning("Haptic feedback failed", exc_info=True)


def use_favorite_toggle(favorites: Favorites) -> ToggleFavorite:
    """Return the one star handler of a list: ``await on_toggle(session_id)`` (D-172).

    A hook for the component that owns a list and already calls ``use_favorites()``;
    rows never call it. The handler is made once (``use_callback(..., [])``), so it is
    the same object on every render and memoised rows given it stay skipped (D-153).
    It closes over the store, the page, the services and the settings, which all live
    as long as the session. A tap shows the change at once (the store assigns before
    it saves), then:

    - an add gives a selection click (``HapticFeedback``, ux.md §4.5);
    - a removal shows "Removed from My schedule" with Undo;
    - an edit that was not saved shows "Couldn't save your change" instead, keeping
      Undo when the edit was a removal.

    Args:
        favorites: The list owner's ``use_favorites()`` store.

    Returns:
        The handler; it reports an unexpected error rather than raising (D-163).
    """
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def toggle(session_id: str) -> None:
        change = await favorites.toggle(svc.storage, session_id)
        if change.added:
            await selection_click(svc.haptics)
        _announce(page, favorites, svc.storage, change, keep=prefs.screen_reader)

    return ft.use_callback(toggle, [])


def _announce(
    page: ft.Page,
    favorites: Favorites,
    storage: Storage,
    change: Change,
    *,
    keep: bool,
) -> None:
    """Show an edit's one SnackBar (``feedback()``), if any, with Undo after a removal.

    Args:
        page: The session's page.
        favorites: The store the edit changed; Undo reverses the edit in it.
        storage: Where the favourites are kept.
        change: The edit.
        keep: A screen reader is on: an Undo SnackBar stays until it is used or
            replaced, as Flutter keeps one with an action (D-184).
    """
    message = feedback(change)
    if message is None:
        return

    @report_errors
    async def undo() -> None:
        reverse = await favorites.undo(storage, change)
        _announce(page, favorites, storage, reverse, keep=keep)

    can_undo = bool(change.removed)
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(message),
            action=ft.SnackBarAction(UNDO, on_click=undo) if can_undo else None,
            behavior=ft.SnackBarBehavior.FLOATING,
            duration=SNACK_BAR_MS,
            # Flutter keeps a SnackBar with an action until it is used; only a
            # screen-reader user needs that time to reach Undo (D-184).
            persist=can_undo and keep,
        )
    )
