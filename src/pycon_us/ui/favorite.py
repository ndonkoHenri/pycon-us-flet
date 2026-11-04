"""The star and what a favourites edit says: saving to My schedule.

`FavoriteButton` is the one favourite control (D-30): a 48 dp star on every session
row and in session detail. A list owner gets the one handler its stars share from
`use_favorite_toggle()`, which saves, gives the selection click and shows the
SnackBar of ux.md §4.4 (D-184). `use_add_all()` is a track page's "Add all to My
schedule" (SCHED-24), with the same SnackBar and its count (D-209); `use_forget()`
is My schedule's "Forget them", the saved sessions the feed dropped (D-329). An edit
that says nothing closes the favourites SnackBar still showing, so a screen reader is never left
with "Removed" about a session saved again (D-251). With a screen reader on, an add says
"Added to My schedule": the star's tap no longer says its state itself (D-355).
`selection_click()` is that click, which search's scope chips give too (ux.md §4.5).

A session's badges, which its row shows beside the star, are `ui/badges.py`'s (D-267).
"""

import logging
from collections.abc import Awaitable, Callable, Iterable
from weakref import WeakKeyDictionary, ref

import flet as ft

from pycon_us.favorites import Change, Favorites
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.ui.focus_back import star_of
from pycon_us.ui.reminder_primer import offer_on_first_favorite
from pycon_us.ui.snack_bars import NOT_SAVED, SNACK_BAR_MS, keep_while_screen_reader

logger = logging.getLogger(__name__)

FAVORITE_LABEL = "Save to My schedule"
"""The star's name for screen readers, the same in both states: its toggle state says
whether the session is saved ("Save to My schedule, switch, on"; D-184)."""

ADD_LABEL = "Add to My schedule"
"""The star's tooltip while the session is not saved (D-30): what a tap does."""

REMOVE_LABEL = "Remove from My schedule"
"""The star's tooltip while the session is saved."""

REMOVED = "Removed from My schedule"
"""The SnackBar after a removal, with Undo (ux.md §4.4): the row may vanish."""

ADDED = "Added to My schedule"
"""The SnackBar after an add, only while a screen reader is on (D-355): what TalkBack
says once the star is filled, where its "on" could come too early (#342)."""

ALREADY_SAVED = "All of them are already in My schedule"
"""The SnackBar after "Add all" when every session was saved already: nothing changed,
so there is no Undo (ux.md §5.10, D-209)."""

UNDO = "Undo"
"""The SnackBar's one action when the edit can be taken back (D-29)."""

_SHOWN: WeakKeyDictionary[ft.Page, ref[ft.SnackBar]] = WeakKeyDictionary()
"""The last favourites SnackBar each page showed, which the next edit closes (D-251).

Weak both ways: a SnackBar holds its page (its Undo, Flet's dismiss handler), so a
strong value would keep a page whose session has ended; the page's dialogs own the
SnackBar while it shows, and drop it once Flet reports it dismissed."""

_EDITS: WeakKeyDictionary[ft.Page, int] = WeakKeyDictionary()
"""How many favourites edits each page has started; only the newest reports (D-251)."""

type ToggleFavorite = Callable[[str], Awaitable[None]]
"""A list's one star handler: `await on_toggle(session_id)`."""

type AddAll = Callable[[Iterable[str]], Awaitable[None]]
"""A track page's "Add all to My schedule": `await add_all(session_ids)`."""

type RemoveAll = Callable[[Iterable[str]], Awaitable[None]]
"""My schedule's "Forget them": `await forget(session_ids)` (D-329)."""


def FavoriteButton(
    selected: bool,
    on_click: ft.ControlEventHandler[ft.IconButton],
    *,
    color: str,
    identifier: str | None = None,
) -> ft.Control:
    """Return the star (D-30): a 48 dp icon button, filled while the session is saved.

    A plain builder, as `badges.TrackBadge`: the memoised row that holds it
    (D-153) passes the scheme's `Tokens.favorite` as `color`. Its tooltip says
    what a tap does, "Add to My schedule" or "Remove from My schedule" (D-27). A
    screen reader gets one node: the stable name `FAVORITE_LABEL`, a switch, and the
    saved state as on or off (D-184). The `IconButton` alone came out nameless and
    stateless in TalkBack's tree (S2), since a tooltip is not an Android content
    description.

    The state is said once: the tooltip is left out of the semantics (iOS would read
    it after the label), and the icon is swapped here rather than through
    `IconButton.selected`, which would add a "selected" to the toggle's "on".

    The tap gives no click of its own (`enable_feedback=False`, D-355): Flutter's
    click sends Android's "clicked" event at once, and TalkBack read the star's state
    from it before Python had changed it, so it sometimes said "on" after a removal
    (#342, F173). The tap's word comes from the SnackBar instead (`feedback()`).

    Args:
        selected: Whether the session is saved to My schedule.
        on_click: What a tap does; it calls the list owner's
            `use_favorite_toggle()` handler with the row's session.
        color: The filled star's colour, `Tokens.favorite`.
        identifier: The node's semantics identifier for UI tests,
            `<screen>.favorite.<session id>` (decisions §M).
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
                # No "clicked" event before the round trip: TalkBack would read the
                # old state from it (#342, F173).
                enable_feedback=False,
                on_click=on_click,
            ),
        )
    )


def feedback(change: Change, *, screen_reader: bool = False) -> str | None:
    """Return what the SnackBar says after a star tap, or None when it says nothing.

    An add says nothing to the eye: the filled star and the selection click are its
    feedback. With a screen reader on it says `ADDED`, since the star's tap does not
    say its state (D-355). A removal says so, because the row may vanish (My
    schedule). An edit that was shown but not saved says that instead, as the tap's
    one SnackBar (ux.md §4.4).

    Args:
        change: What `Favorites.toggle()` or `Favorites.undo()` returned.
        screen_reader: A screen reader is on (`Prefs.screen_reader`).
    """
    if not change.saved:
        return NOT_SAVED
    if change.removed:
        return REMOVED
    return ADDED if screen_reader else None


async def selection_click(haptics: ft.HapticFeedback) -> None:
    """Give the selection click (ux.md §4.5), logging rather than reporting a failure.

    Args:
        haptics: `Services.haptics`.
    """
    try:
        await haptics.selection_click()
    except SERVICE_ERRORS:  # a missed click is not worth an error message
        logger.warning("Haptic feedback failed", exc_info=True)


def use_favorite_toggle(favorites: Favorites) -> ToggleFavorite:
    """Return the one star handler of a list: `await on_toggle(session_id)` (D-172).

    A hook for the component that owns a list and already calls `use_favorites()`;
    rows never call it. The handler is made once (`use_callback(..., [])`), so it is
    the same object on every render and memoised rows given it stay skipped (D-153).
    It closes over the store, the page, the services and the settings, which all live
    as long as the session. A tap shows the change at once (the store assigns before
    it saves), then:

    - an add gives a selection click (`HapticFeedback`, ux.md §4.5);
    - a removal shows "Removed from My schedule" with Undo;
    - an edit that was not saved shows "Couldn't save your change" instead, keeping
      Undo when the edit was a removal;
    - an add, with a screen reader on, shows "Added to My schedule" (D-355);
    - an edit that says nothing (an add or an Undo without a screen reader) closes
      the favourites SnackBar still showing, as a new one replaces it (D-251);
    - an add that was saved shows the reminders primer, once, when it was never
      answered (`ui.reminder_primer`, D-61, D-395).

    Args:
        favorites: The list owner's `use_favorites()` store.

    Returns:
        The handler; it reports an unexpected error rather than raising (D-163).
    """
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def toggle(session_id: str) -> None:
        edit = _begin(page)
        # Before the add: on Now its render replaces the star (focus_back, D-395).
        star = (
            star_of(page, session_id) if prefs.reminders.primer == "unasked" else None
        )
        change = await favorites.toggle(svc.storage, session_id)
        if change.added:
            await selection_click(svc.haptics)
        _announce(page, favorites, svc, prefs, change, edit=edit)
        if change.added and change.saved:  # a star's add only: never Undo or Add all
            await offer_on_first_favorite(page, svc, prefs, star=star)

    return ft.use_callback(toggle, [])


def _announce(
    page: ft.Page,
    favorites: Favorites,
    svc: Services,
    prefs: Prefs,
    change: Change,
    *,
    edit: int,
) -> None:
    """Report a star edit through `_report()`: `feedback()`'s SnackBar, or none.

    A removal's SnackBar has Undo; an edit that says nothing closes the last (D-251).
    With a screen reader on, an add (an Undo's too) says `ADDED` (D-355).

    Args:
        page: The session's page.
        favorites: The store the edit changed; Undo reverses the edit in it.
        svc: The session's services: where the favourites are kept.
        prefs: The session's `Prefs`: with a screen reader on, an add says
            `ADDED` and an Undo SnackBar stays (D-355, D-184).
        change: The edit.
        edit: The edit's number from `_begin()`.
    """

    @report_errors
    async def undo() -> None:
        edit = _begin(page)
        reverse = await favorites.undo(svc.storage, change)
        _announce(page, favorites, svc, prefs, reverse, edit=edit)

    undoes = undo if change.removed else None
    message = feedback(change, screen_reader=prefs.screen_reader)
    _report(page, message, undo=undoes, svc=svc, prefs=prefs, edit=edit)


def added_feedback(change: Change) -> str:
    """Return what the SnackBar says after "Add all to My schedule" (ux.md §5.10).

    It counts only the sessions the tap saved, never those saved before (D-172):
    "Added 16 sessions", "Added 1 session", or `ALREADY_SAVED` when there were none.
    An edit that was shown but not saved says `NOT_SAVED` instead (ux.md §4.4).

    Args:
        change: What `Favorites.add_many()` returned.
    """
    if not change.saved:
        return NOT_SAVED
    count = len(change.added)
    if not count:
        return ALREADY_SAVED
    return f"Added {count} {'session' if count == 1 else 'sessions'}"


def use_add_all(favorites: Favorites) -> AddAll:
    """Return a track page's "Add all to My schedule": `await add_all(ids)` (D-209).

    A hook for the page that already calls `use_favorites()`. Unlike
    `use_favorite_toggle()`'s handler it is not memoised: no memoised control
    receives it, since the page builds its menu on every render (D-153). No dialog
    first: the add is reversible (D-29). It saves every id at once
    (`Favorites.add_many()`), gives the selection click when it saved any, and shows
    one SnackBar, `added_feedback()`'s, with Undo whenever it saved some, also when
    the write failed. Undo takes back only what the tap added (`Favorites.undo()`),
    so the list is again what it was, and says nothing more, as a star's Undo does,
    closing the SnackBar (D-251), unless its own write fails ("Couldn't save your
    change", with no Undo of the Undo: the menu offers the add again).

    Args:
        favorites: The page's `use_favorites()` store.

    Returns:
        The handler; it reports an unexpected error rather than raising (D-163).
    """
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def add_all(session_ids: Iterable[str]) -> None:
        edit = _begin(page)
        change = await favorites.add_many(svc.storage, session_ids)
        if change.added:
            await selection_click(svc.haptics)

        @report_errors
        async def undo() -> None:
            edit = _begin(page)
            reverse = await favorites.undo(svc.storage, change)
            message = None if reverse.saved else NOT_SAVED
            _report(page, message, undo=None, svc=svc, prefs=prefs, edit=edit)

        undoes = undo if change.added else None
        message = added_feedback(change)
        _report(page, message, undo=undoes, svc=svc, prefs=prefs, edit=edit)

    return add_all


def use_forget(favorites: Favorites) -> RemoveAll:
    """Return My schedule's "Forget them": `await forget(ids)` (D-329).

    It removes every id at once (`Favorites.remove_many()`) and says so as a star's
    removal does, through `_announce()`: "Removed from My schedule" with Undo, which
    saves them all again, or "Couldn't save your change". No dialog: it is reversible
    (D-29). Not memoised, as `use_add_all()`: no memoised control receives it.

    Args:
        favorites: The screen's `use_favorites()` store.

    Returns:
        The handler; it reports an unexpected error rather than raising (D-163).
    """
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def forget(session_ids: Iterable[str]) -> None:
        edit = _begin(page)
        change = await favorites.remove_many(svc.storage, session_ids)
        _announce(page, favorites, svc, prefs, change, edit=edit)

    return forget


def _begin(page: ft.Page) -> int:
    """Start a favourites edit on the page: return its number, before its first await."""
    edit = _EDITS.get(page, 0) + 1
    _EDITS[page] = edit
    return edit


def _report(
    page: ft.Page,
    message: str | None,
    *,
    undo: Callable[[], Awaitable[None]] | None,
    svc: Services,
    prefs: Prefs,
    edit: int,
) -> None:
    """Report a favourites edit: its SnackBar, or none, never the last edit's (D-251).

    A message shows a floating SnackBar for 4 s, its one action Undo when given
    (D-29). Flet's `SnackBarControl` removes the current SnackBar before it shows
    one (`snack_bar.dart`), so a new message replaces the last. An edit that says
    nothing closes the last favourites SnackBar itself, while it still shows: with a
    screen reader it stays until used (D-184), and "Removed from My schedule" must not
    outlive the add or Undo that saved the session again (#334). It closes that
    SnackBar only, never `page.pop_dialog()`'s top dialog (ux.md §4.5); and only
    when nothing is shown, since a close and a show sent together each remove the
    current SnackBar after the frame, in an order Flet does not promise. Edits
    overlap (a second tap while the first awaits its write or its haptic click), so
    only the page's newest edit reports: an older one, finishing late, must neither
    close a newer edit's SnackBar nor show one over its silence. The newest writes the
    whole set (`Favorites`), so its result is the one that counts.

    Args:
        page: The session's page.
        message: What it says, or None when the edit says nothing.
        undo: Undo's handler, or None for a SnackBar without an action.
        svc: The session's services, which watch a screen reader's SnackBar.
        prefs: The session's `Prefs`: while a screen reader is on, an Undo
            SnackBar stays until it is used, replaced, closed by the next edit, or
            no screen reader is on (D-184, D-251, D-356). A SnackBar without Undo,
            `ADDED` among them (D-355), goes after its 4 s and is not watched.
        edit: The edit's number from `_begin()`, taken before its first await.
    """
    if _EDITS.get(page) != edit:
        return  # a newer edit has started: its report, or its silence, counts
    if message is None:
        shown = _SHOWN.pop(page, None)
        last = shown() if shown is not None else None
        if last is not None and last.open:  # Flet sets open False once it has gone
            last.open = False
            last.update()
        return
    keep = undo is not None and prefs.screen_reader
    bar = ft.SnackBar(
        content=ft.Text(message),
        action=ft.SnackBarAction(UNDO, on_click=undo) if undo else None,
        behavior=ft.SnackBarBehavior.FLOATING,
        duration=SNACK_BAR_MS,
        # Flutter keeps a SnackBar with an action until it is used; only a
        # screen-reader user needs that time to reach Undo (D-184).
        persist=keep,
    )
    page.show_dialog(bar)
    _SHOWN[page] = ref(bar)
    if keep:
        keep_while_screen_reader(bar, svc, prefs)
