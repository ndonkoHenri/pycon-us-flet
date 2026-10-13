"""The chrome every screen shares: ``AppScaffold``, ``SectionHeader`` and ``search_button()``.

``AppScaffold`` builds each screen's View (architecture §5.5): a surface ``AppBar`` with
the screen's title, left-aligned and always visible (D-10, D-28), the Material back arrow
on pushed Views, the bottom bar (``ui.navigation``) and the Back rules on tab roots
(D-13, D-17, D-142, D-144), and the body in a ``SafeArea`` (D-12, D-113). The status- and
navigation-bar style comes from the theme (``theme.overlay_style()``, D-151): Flet's
``AppBar`` applies it, so a screen never sets one. The tablet rail with the 720/840 dp
content widths joins in P2 (#30).

``SectionHeader`` is the heading of a group of rows. The status strip and the minute
tick are ``ui.status_strip`` (D-200).
"""

import asyncio
import logging

import flet as ft

from pycon_us.locations import TAB_ROOTS, is_top_view, parent_of
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME, Storage
from pycon_us.state import Source, ViewMemory, use_conference
from pycon_us.ui.navigation import TABS, Retap, navigation_bar

logger = logging.getLogger(__name__)


def AppScaffold(
    *,
    title: str,
    body: ft.Control,
    actions: list[ft.Control] | None = None,
    on_retap: Retap | None = None,
    fab: ft.FloatingActionButton | None = None,
) -> ft.View:
    """Return a screen's View: the app bar, the bottom bar, the Back rules and the body.

    A plain builder that calls hooks, so a screen calls it exactly once per render, in
    every branch (hooks are unconditional, D-70). It records the top View's route for
    the start route (D-143), and places the body in ``Shown``, which logs D-112's
    content line (D-165).

    On a tab root the View gets the bottom bar (D-144); pushed Views get the back arrow
    instead (D-10). Back on a root other than Now goes to Now, and Back on Now is left
    to the system, which leaves the app (D-17, D-142).

    Args:
        title: The screen's name: the app bar's title and, for screen readers, the
            page's level-1 heading (D-211). On a tab root it carries the identifier
            ``<tab>.title`` for UI flows (D-170). Empty on a detail page whose own
            title, in the page, is its level-1 heading (ux.md §5.5): no heading then.
        body: What the View shows under the app bar, usually an ``expand=True``
            ``ListView``; it is placed in a ``SafeArea``, clear of the notch, the
            home indicator and the navigation bar in either orientation.
        actions: The app bar's actions, e.g. ``search_button()``; each icon-only one
            has a tooltip, its accessible name (D-27).
        on_retap: A tab root's action when its active tab is tapped again, usually
            the one ``ui.navigation.use_scroll_to_top()`` returns; ignored on pushed
            Views, which have no bar.
        fab: The screen's floating action button, if any: the Schedule's "Now"
            (ux.md §5.2). The body leaves room for it at its end.

    Returns:
        The View for this route level.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    is_root = view_path in TAB_ROOTS
    back_to_now = is_root and view_path != "/now"
    if is_top_view(page.route, view_path):  # where a new session returns (D-143)
        svc.memory.last_location = page.route

    @report_errors
    def go_back() -> None:
        # /search returns to its opener, any other View one level up (D-19).
        page.navigate(parent_of(view_path, svc.memory.search_base))

    @report_errors
    async def leave_for_now(e: ft.Event[ft.View]) -> None:
        page.navigate("/now")
        await e.control.confirm_pop(False)  # this View stays; Now replaces the root

    @report_errors
    async def switch_tab(e: ft.Event[ft.NavigationBar]) -> None:
        # Flutter reports the active destination too, so a re-tap lands here (S4).
        root = TAB_ROOTS[e.control.selected_index]
        if root != view_path:
            page.navigate(root)  # roots share one View key: a swap, not a push (D-142)
        elif on_retap is not None:
            await on_retap()

    back_arrow = ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back)
    title_control: ft.Control = ft.Text(title)
    if title:
        # Flutter's AppBar flags its title a header without a level, which neither
        # screen reader takes for a heading (F49): the level makes it the page's
        # level-1 heading (D-211). The identifier tells UI flows which root shows
        # (D-170). An unlabelled Semantics merges both into the title's own node, as
        # the bar's do (D-166).
        title_control = ft.Semantics(
            header=True,
            heading_level=1,
            identifier=(
                TABS[TAB_ROOTS.index(view_path)].title_identifier if is_root else None
            ),
            content=title_control,
        )
    return ft.View(
        route="/" if is_root else view_path,  # roots share a key: no transition (D-142)
        padding=0,
        appbar=ft.AppBar(
            title=title_control,
            center_title=False,  # as the theme says; iOS would centre it (D-10)
            # Flutter would imply the iOS chevron on iOS; the Material arrow instead.
            automatically_imply_leading=False,
            leading=None if is_root else back_arrow,
            actions=actions or [],
        ),
        # On roots only: on pushed Views the bar moved with the page (D-144).
        navigation_bar=navigation_bar(view_path, switch_tab) if is_root else None,
        floating_action_button=fab,
        can_pop=not back_to_now,
        on_confirm_pop=leave_for_now if back_to_now else None,
        controls=[ft.SafeArea(expand=True, content=Shown(body))],
    )


@ft.component
def Shown(body: ft.Control) -> ft.Control:
    """Return ``body`` unchanged, and log D-112's content line once per feed version.

    The line is ``Content shown: <source> feed, version <n>``, logged from the first
    screen that renders a version (``Services.shown_versions``, D-165), through
    ``log_when_shown()``. It is a component of
    its own so that only it reads ``Conference``: a refresh re-renders this leaf, which
    hands back the same ``body``, and not the screen around it.

    Args:
        body: The screen's body.
    """
    svc = use_services()
    conference = use_conference()
    version, source = conference.version, conference.source  # what this render shows

    @report_errors
    async def log_shown() -> None:
        if version in svc.shown_versions:  # another screen showed it first
            return
        svc.shown_versions.add(version)
        # A newer version re-runs this effect, and Flet cancels the run in progress (an
        # unmount does not: no cleanup). This version was rendered all the same, and the
        # first line marks the cold start, so the shield lets the line finish.
        await asyncio.shield(log_when_shown(svc.storage, source, version))

    ft.use_effect(log_shown, [version])
    return body


@report_errors
async def log_when_shown(storage: Storage, source: Source, version: int) -> None:
    """Log D-112's content line once a SharedPreferences round trip has returned.

    The round trip goes after the render's patch, so Flutter has the content when the
    line is logged (a proxy: S1 saw it 0.2-0.3 s after the pixels).

    Args:
        storage: The session's ``Storage``.
        source: Where the shown feed came from.
        version: The shown feed version.
    """
    await storage.get(THEME)
    logger.info("Content shown: %s feed, version %d", source, version)


def search_button(memory: ViewMemory, scope: str) -> ft.IconButton:
    """Return the app bar action that opens the global search with a preset scope (D-19).

    It records the opener's location, query included, so Back from search returns
    there, and clears the last query, so each search starts empty (D-193).

    Args:
        memory: The process's ``ViewMemory``.
        scope: ``all``, ``sessions``, ``speakers`` or ``rooms``.
    """
    page = ft.context.page

    @report_errors
    def open_search() -> None:
        memory.search_base = page.route
        memory.search_query = ""  # a new search; Back to its results keeps the old one
        page.navigate(f"/search?scope={scope}")

    return ft.IconButton(ft.Icons.SEARCH, tooltip="Search", on_click=open_search)


def SectionHeader(
    text: str,
    *,
    level: int = 2,
    top: int = 16,
    theme_style: ft.TextThemeStyle = ft.TextThemeStyle.TITLE_SMALL,
    color: ft.ColorValue = ft.Colors.PRIMARY,
    leading: ft.Control | None = None,
    spoken: str | None = None,
) -> ft.Control:
    """Return the heading of a group of rows: a day, a letter, a section (ux.md §3.9).

    Not sticky (U2). A heading for screen readers, so they can jump group by group:
    TalkBack and VoiceOver take a heading from its level, not the flag (F40, D-211).

    Args:
        text: The heading, in sentence case.
        level: Its place in the page's outline: 2, a section under the page's
            level-1 title (the app bar's, or a detail page's own, ux.md §5.5), or 3
            under a level-2 heading (search's days under "Sessions", D-193).
        top: The space above it: 16 dp where it opens a group in a list; 0 on a
            detail page, whose list already puts 24 dp between sections.
        theme_style: Its type: ``TITLE_SMALL``, or ``TITLE_MEDIUM`` for a heading that
            holds headings of its own (search's "Sessions" over its days, D-193).
        color: Its colour role: ``primary``, or ``on_surface`` with ``TITLE_MEDIUM``.
        leading: A decorative mark before the text, such as Now's live dot: a
            control without a label (a shape, an unlabelled icon), so the heading
            still reads as ``text``.
        spoken: What a screen reader says instead of ``text``, when it differs:
            "Up next, 11:30 AM" for "Up next · 11:30 AM".
    """
    label: ft.Control = ft.Text(
        text,
        theme_style=theme_style,
        color=color,
        semantics_label=spoken,
        # Beside a mark, the row's room: in a row a text gets unbounded width and
        # would overflow instead of wrapping at large text.
        expand=leading is not None,
    )
    if leading is not None:
        label = ft.Row(
            [leading, label],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Semantics(
        header=True,
        heading_level=level,
        content=ft.Container(
            label,
            padding=ft.Padding.only(left=16, top=top, right=16, bottom=8),
        ),
    )
