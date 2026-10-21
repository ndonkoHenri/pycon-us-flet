"""My schedule's extras (ux.md §5.6): the app bar's overflow and the all-over notice.

- **The overflow** ("More options", D-289): Export to calendar (.ics), every saved
  session still in the schedule in one file, ``pycon-us-<year>-my-schedule.ics``, each
  event with its alarm (SESS-05). It goes to the calendar by session detail's Add to
  calendar route (``services.calendar``, D-272): iOS's "Add All" sheet, or Android's
  save dialog and a SnackBar. With nothing saved there is nothing to export, so the
  screen shows no overflow.
- **The all-over notice** heads the list when every saved session has ended (D-191).
- **The dropped notice** heads it when some saved sessions are no longer in the
  schedule (D-329): how many, that they come back if the feed lists them again, "See
  what changed" (Schedule changes) when the change log holds one's removal, and
  "Forget it" or "Forget them".

The screen itself is ``screens/my_schedule.py``; these left it to keep it near 400
lines (D-66).
"""

from collections.abc import Awaitable, Callable, Collection, Iterable

import flet as ft

from pycon_us import clock
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import ChangeKind
from pycon_us.core.ics import calendar_file
from pycon_us.core.models import Session
from pycon_us.services import use_services
from pycon_us.services.calendar import add_to_calendar
from pycon_us.services.errors import report_errors
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.menus import menu_item, overflow_menu
from pycon_us.ui.semantics import named

SCREEN = "my_schedule"
"""The screen's name in its semantics identifiers (decisions §M)."""

EXPORT = "Export to calendar (.ics)"
"""The overflow's export item (ux.md §5.6), the same words on both platforms (D-272)."""

ALL_OVER = "All your saved sessions are over"
SEE_TODAY = "See what's on today"
CONFERENCE_OVER = "{name} is over. Your saved sessions stay here."

SEE_CHANGES = "See what changed"
"""The dropped notice's link to Schedule changes (D-329)."""


def export_slug(year: int) -> str:
    """Return the export's file name without ``.ics``: ``pycon-us-2026-my-schedule``.

    The year keeps one year's export from looking like another's in the Files app.

    Args:
        year: The conference year.
    """
    return f"pycon-us-{year}-my-schedule"


@ft.component
def ScheduleMenu(sessions: tuple[Session, ...]) -> ft.Control:
    """The app bar's overflow ("More options"): Export to calendar (.ics).

    The item is disabled while the calendar's sheet or the save dialog is up, so a
    second tap does not serve or save the file twice; in place, so the button and the
    item keep their nodes and the screen reader's focus comes back to the button when
    the menu closes (D-182, D-225). Its label wraps at 200 % text (``menu_item()``,
    D-233). Whatever happens is said by ``add_to_calendar()``, on this View (D-210).

    Args:
        sessions: Every saved session still in the schedule (``Agenda.sessions``); at
            least one, since the screen shows no overflow without.
    """
    svc = use_services()
    exporting, set_exporting = ft.use_state(False)

    @report_errors
    async def export() -> None:
        year = svc.year.conference.year
        data = calendar_file(sessions, year=year, now=clock.now())
        set_exporting(True)
        try:
            await add_to_calendar(svc, export_slug(year), data)
        finally:
            set_exporting(False)

    item = menu_item(
        ft.Icons.EVENT_AVAILABLE_OUTLINED,  # session detail's Add to calendar's icon
        EXPORT,
        export,
        identifier=f"{SCREEN}.export",
        disabled=exporting,
    )
    return overflow_menu(f"{SCREEN}.overflow", [item])


def all_over(
    on_see_today: Callable[[], None] | None = None, *, body: str | None = None
) -> ft.Control:
    """Return the notice that heads the list when every saved session has ended.

    Compact and start-aligned, its text on the fold tile's text column, rather than
    the full-screen empty state: the "Earlier days" tile under it is still content and
    should not be pushed to the middle of the screen (ux.md §5.6).

    Args:
        on_see_today: What "See what's on today" does, while today is a conference
            day; None after the conference, when Now has nothing on today.
        body: A second line, after the conference.
    """
    texts: list[ft.Control] = [
        ft.Semantics(  # a container of its own, as EmptyState's title (D-182)
            header=True,
            heading_level=2,  # a section under the page's title, as the day headings (D-211)
            container=True,
            content=ft.Text(ALL_OVER, theme_style=ft.TextThemeStyle.TITLE_SMALL),
        )
    ]
    if body is not None:
        texts.append(
            ft.Text(
                body,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    column: list[ft.Control] = [
        ft.Semantics(
            identifier=f"{SCREEN}.all_over",
            container=True,
            live_region=True,
            content=ft.Column(texts, spacing=4),
        )
    ]
    if on_see_today is not None:
        column.append(
            ft.FilledTonalButton(
                SEE_TODAY,
                on_click=on_see_today,
                # Material's 100 % padding at every size (D-344).
                style=ft.ButtonStyle(padding=LABEL_PADDING),
                elevation=0,  # with a style, Flet lifts it to 1 (D-344)
            )
        )
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.EVENT_AVAILABLE_OUTLINED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Column(column, spacing=12, expand=True),
            ],
            spacing=16,  # the text on the fold tile's text column, 56 dp in
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.only(left=16, top=16, right=16, bottom=8),
    )


def dropped_title(count: int) -> str:
    """Return the dropped notice's title: "1 saved session is no longer in the schedule".

    Args:
        count: How many saved ids the feed no longer lists; at least one.
    """
    if count == 1:
        return "1 saved session is no longer in the schedule"
    return f"{count} saved sessions are no longer in the schedule"


def dropped_body(count: int) -> str:
    """Return the dropped notice's second line: they come back if the feed lists them.

    Args:
        count: How many saved ids the feed no longer lists; at least one.
    """
    if count == 1:
        return "If the schedule lists it again, it comes back here."
    return "If the schedule lists them again, they come back here."


def forget_label(count: int) -> str:
    """Return the dropped notice's removal button: "Forget it" or "Forget them".

    Args:
        count: How many saved ids the feed no longer lists; at least one.
    """
    return "Forget it" if count == 1 else "Forget them"


def logged(dropped: Collection[str], batches: Iterable[Batch]) -> bool:
    """Return whether the change log holds the removal of one of ``dropped`` (D-329).

    Only then does Schedule changes say anything about them, so only then does the
    notice link there: the log keeps 14 days and is deleted with a feed URL change.

    Args:
        dropped: The saved ids the feed no longer lists.
        batches: The change log's batches (``ChangeLog.batches``).
    """
    return any(
        change.kind is ChangeKind.REMOVED and change.id in dropped
        for batch in batches
        for change in batch.changes
    )


def dropped_notice(
    count: int,
    *,
    on_forget: Callable[[], Awaitable[None]],
    on_see_changes: Callable[[], None] | None,
) -> ft.Control:
    """Return the notice that heads the list when some saved sessions were dropped.

    Compact and start-aligned on the fold tile's text column, as ``all_over()``: the
    saved sessions still in the schedule stay the content (D-329). Its words are one
    live-region node, a level-2 heading whose label is the title then the body, so
    the label changes when the count does and a screen reader says it.

    The label is explicit and the texts are left out of the semantics tree, because
    a merge of the texts reads the body first. Flet's ``Semantics`` always states
    ``enabled`` (F42), and two configurations that both state it conflict
    (``Tristate.hasConflict``), so a heading ``Semantics`` inside the live region
    becomes a child node; the live region keeps the body as its own label, and a
    merge puts a node's own label before its children's (D-329).

    With ``count`` 0 it is the same node, quiet: a hidden 1 dp node with no words.
    The list always has it, so the node exists before the first dropped session:
    Android's engine sends a live region's change only for a node it had in its
    previous update (F61, D-241), and a notice that mounted with its words would go
    unsaid. Empty is not enough to be quiet: Flet's ``Semantics`` always states
    ``enabled``, which makes the node focusable on Android, a blank TalkBack stop
    (F95). Hidden, Android keeps the node but leaves it out of the tree a reader
    walks; the update that shows it also changes its label, so it is announced.

    Args:
        count: How many saved ids the feed no longer lists; 0 for the quiet node.
        on_forget: What "Forget them" does: unsave those ids, with Undo.
        on_see_changes: What "See what changed" does, while the change log holds one
            of the removals (``logged()``); None leaves the button out.
    """
    shown = count > 0
    title, body = (dropped_title(count), dropped_body(count)) if shown else ("", "")
    words = ft.Semantics(
        identifier=f"{SCREEN}.dropped_notice",
        container=True,
        live_region=True,
        hidden=not shown,  # quiet: no blank TalkBack stop (F95)
        label=f"{title}\n{body}" if shown else None,  # in reading order
        header=shown,
        heading_level=2 if shown else None,
        exclude_semantics=True,  # the label says the texts, in their order
        content=(
            ft.Column(
                [
                    ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_SMALL),
                    ft.Text(
                        body,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
            )
            if shown
            else ft.Container(width=1, height=1)  # a node needs a size (F61)
        ),
    )
    buttons: list[ft.Control] = []
    if shown and on_see_changes is not None:
        button = ft.TextButton(SEE_CHANGES, on_click=on_see_changes)
        buttons.append(named(f"{SCREEN}.see_changes", button))
    if shown:
        forget = ft.TextButton(forget_label(count), on_click=on_forget)
        buttons.append(named(f"{SCREEN}.forget", forget))
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.EVENT_BUSY_OUTLINED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    visible=shown,
                ),
                ft.Column(
                    # A row that wraps at large text, under the words.
                    [words, ft.Row(buttons, wrap=True, spacing=8, visible=shown)],
                    spacing=8,
                    expand=True,
                ),
            ],
            spacing=16,  # the text on the fold tile's text column, 56 dp in
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=(
            ft.Padding.only(left=16, top=16, right=16, bottom=8)
            if shown
            else ft.Padding.all(0)
        ),
    )
