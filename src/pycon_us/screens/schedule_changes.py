"""Schedule changes (``…/changes/<year>``): what the refreshes changed (NEW-04, D-47, D-255).

A drill level, pushed on the View that opens it, so Back returns there (D-255). Under
the app bar's "Schedule changes", "Affects My schedule" first, then "All changes"
(level-2 headings), each grouped by when the refresh found its changes, newest first
(level-3 headings: "Today, 10:42 AM"). The words are ``core/change_views.py``'s: each
item shows its kind's icon (decorative), the session's newest title and "old → new",
the old value struck through and the new one in ``W_600``, and reads as one sentence
that never relies on the strikethrough (ux.md §6.4). The star beside it is its own
stop, with Undo as everywhere (D-184, D-251).

A tap pushes the session on top of the list. A removed session's item is not a link,
since its id would open the not-found state (D-186): it shows its last time and room
with "Removed from the latest schedule" inline and keeps its star, so a saved session
the feed dropped can be let go here (D-255, #215).

The sections are sorted by the sessions saved when the list opened (or when the
favourites load): a star tap changes the item's star and phrase, never its place, so a
screen reader's focus is not moved away from the item just tapped. An id that is not
the active year shows the not-found state on its own level (D-186, D-255).

An unseen item has a dot and reads "New: " first; the list marks what it shows seen
after 2 s, and the overflow has Mark all as seen (``schedule_changes_seen.py``).
"""

import flet as ft

from pycon_us.change_log import use_change_log
from pycon_us.clock import now
from pycon_us.core.change_views import (
    REMOVED_NOTE,
    ChangeView,
    item_phrase,
    sections,
)
from pycon_us.core.diff import ChangeKind
from pycon_us.favorites import use_favorites
from pycon_us.locations import drill_href, is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.screens.schedule_changes_seen import (
    FADE_MS,
    mark_all_menu,
    use_seen_marks,
    with_dot,
)
from pycon_us.screens.stub import not_found
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.favorite import FavoriteButton, ToggleFavorite, use_favorite_toggle
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import semantics_key
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, sides, use_margin

SCREEN = "changes"
"""The screen's name in its semantics identifiers (decisions §M)."""

TITLE = "Schedule changes"
"""The app bar's title, the page's level-1 heading (D-211)."""

EMPTY = "No changes yet"
"""The empty state's title (ux.md §4.6)."""

EMPTY_BODY = "When a refresh changes the schedule, what changed shows here."
"""The empty state's second line."""

NOT_FOUND = "These schedule changes aren't in the app"
"""The empty state of an id that is not the active year (ux.md §4.6, D-255)."""

ICONS = {
    ChangeKind.ADDED: ft.Icons.NEW_RELEASES_OUTLINED,
    ChangeKind.REMOVED: ft.Icons.EVENT_BUSY_OUTLINED,
}
"""Each kind's leading icon; a time, room or title change has ``CHANGE_CIRCLE_OUTLINED``."""

ARROW = " → "
"""Between an item's old and new values on screen."""


@ft.component
def ScheduleChanges(year: str) -> ft.View:
    """The change log of the active year, saved sessions first.

    Args:
        year: The drill id, unquoted: the conference year the log is kept for.
    """
    page = ft.context.page
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    change_log = use_change_log()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    prefs = use_prefs()
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    zone = svc.year.conference.zone
    # The saved set the sections are sorted by: taken once the favourites have loaded,
    # so a star tap never moves its item to the other section.
    opened_with = ft.use_memo(lambda: favorites.ids, [favorites.loaded])
    shown = ft.use_memo(
        lambda: sections(change_log.batches, opened_with, zone, now(), use_24h=use_24h),
        [change_log.batches, opened_with, use_24h],
    )

    current = year == str(svc.storage.year)
    unseen = ft.use_memo(
        lambda: tuple(b for b in change_log.batches if not b.seen) if current else (),
        [change_log.batches, current],
    )
    # Shown only as the top View: a session pushed on it keeps it mounted (D-164).
    on_top = is_top_view(page.route, ft.use_view_path())
    use_seen_marks(change_log, svc.storage, prefs, svc.closed, unseen if on_top else ())
    fade_ms = prefs.motion_ms(FADE_MS)

    @report_errors
    def open_schedule() -> None:
        page.navigate("/schedule")

    items: list[ft.Control]
    if not current:
        items = [
            not_found(
                NOT_FOUND,
                icon=ft.Icons.LINK_OFF_OUTLINED,
                action="Open schedule",
                location="/schedule",
                identifier=f"{SCREEN}.not_found",
            )
        ]
    elif not shown:
        items = [
            EmptyState(
                EMPTY,
                icon=ft.Icons.HISTORY,
                body=EMPTY_BODY,
                action="Open schedule",
                on_action=open_schedule,
                identifier=f"{SCREEN}.empty",
            )
        ]
    else:
        items = []
        for section in shown:
            items.append(SectionHeader(section.title))
            for group in section.groups:
                items.append(SectionHeader(group.heading, level=3, top=8))
                stamp = group.batch.detected_at.isoformat()
                items.extend(
                    ChangeItem(
                        view,
                        view.change.id in favorites.ids,
                        not group.batch.seen,
                        on_toggle,
                        tokens,
                        fade_ms,
                        key=f"{stamp}/{view.change.id}/{view.change.kind}",
                    )
                    for view in group.views
                )
    return AppScaffold(
        title=TITLE,
        body=ft.ListView(items, expand=True, padding=sides(margin)),
        actions=[mark_all_menu(change_log, svc.storage, screen=SCREEN)]
        if current
        else None,
    )


def ChangeItem(
    view: ChangeView,
    saved: bool,
    unseen: bool,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    fade_ms: int,
    *,
    key: str,
) -> ft.Control:
    """Return one change: its icon, title and "old → new", read as one sentence, and a star.

    A memoised component (D-153): a star tap re-renders only the items of that session.

    Args:
        view: The change's view, the same object while the log and the clock format
            stay.
        saved: Whether the session is in My schedule.
        unseen: Whether the item's batch is unseen: a dot, and "New: " first.
        on_toggle: The list's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens (D-150), for the star's colour.
        fade_ms: How long the dot fades once seen (``prefs.motion_ms()``).
        key: Unique in the list: the batch's detection time, the id and the kind.
    """
    # ft.component's typing (its ParamSpec) leaves out the key= its wrapper takes.
    return _ChangeItem(view, saved, unseen, on_toggle, tokens, fade_ms, key=key)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _ChangeItem(
    view: ChangeView,
    saved: bool,
    unseen: bool,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    fade_ms: int,
) -> ft.Control:
    """The body of ``ChangeItem``; it runs only when the props change (F34)."""
    page = ft.context.page
    view_path = ft.use_view_path()
    change = view.change
    removed = change.kind is ChangeKind.REMOVED
    ident = f"{semantics_key(change.id)}.{change.kind}"

    @report_errors
    def open_session() -> None:
        page.navigate(drill_href(view_path, "session", change.id))

    @report_errors
    async def star() -> None:
        await on_toggle(change.id)

    tile = ft.ListTile(
        leading=with_dot(
            ft.Icon(ICONS.get(change.kind, ft.Icons.CHANGE_CIRCLE_OUTLINED)),
            unseen=unseen,
            fade_ms=fade_ms,
        ),
        title=ft.Text(view.title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
        subtitle=change_line(view),
        content_padding=ft.Padding.only(left=16, right=4),
    )
    text = ft.Semantics(
        label=item_phrase(view, saved=saved, unseen=unseen),
        identifier=f"{SCREEN}.change.{ident}",
        button=not removed,  # a removed session opens nothing (D-255)
        # The sentence replaces the texts, which would otherwise be read after it.
        exclude_semantics=True,
        content=tile,
    )
    return ft.Row(
        [
            # The tap sits outside the excluded subtree, so the merged node keeps the
            # tap action a screen reader activates, as on a session row.
            ft.MergeSemantics(
                expand=True,
                content=ft.Container(
                    text,
                    ink=not removed,
                    on_click=None if removed else open_session,
                ),
            ),
            ft.Container(
                FavoriteButton(
                    saved,
                    star,
                    color=tokens.favorite,
                    identifier=f"{SCREEN}.favorite.{ident}",
                ),
                padding=ft.Padding.only(top=4, right=4),
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def change_line(view: ChangeView) -> ft.Text:
    """Return an item's second line: the old value struck through, "→", the new in bold.

    An addition has only its new value; a removal its last value, struck through,
    then "Removed from the latest schedule", so the strikethrough is never the only
    cue (ux.md §6.4). Supporting text, in ``on_surface_variant``.

    Args:
        view: The change's view.
    """
    old = ft.TextSpan(
        view.old, style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
    )
    new = ft.TextSpan(view.new, style=ft.TextStyle(weight=ft.FontWeight.W_600))
    if not view.old:
        spans = [new]
    elif not view.new:
        spans = [old, ft.TextSpan(f" · {REMOVED_NOTE}")]
    else:
        spans = [old, ft.TextSpan(ARROW), new]
    return ft.Text(
        spans=spans,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
