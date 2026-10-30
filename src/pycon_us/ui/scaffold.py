"""The chrome every screen shares: ``AppScaffold``, the headings, ``search_button()``.

``AppScaffold`` builds each screen's View (architecture §5.5): a surface ``AppBar`` with
the screen's title, left-aligned and always visible (D-10, D-28), the Material back arrow
on pushed Views, the bottom bar or, from 600 dp, the rail (``ui.navigation``) and the
Back rules on tab roots (D-13, D-17, D-142, D-144, D-277), and the body in a
``SafeArea`` (D-12, D-113). The status- and navigation-bar style comes from the theme
(``theme.overlay_style()``, D-151): Flet's ``AppBar`` applies it, so a screen never sets
one. The 720/840 dp content widths are each screen's own, ``ui.widths.use_margin()``
(D-305): the screen builds its list before it calls ``AppScaffold``.

``SectionHeader`` is the heading of a group of rows; a detail page's own title is
``ui.page_title.PageTitle`` (D-328). The status strip and the minute tick are ``ui.status_strip`` (D-200).
"""

import asyncio
import logging

import flet as ft

from pycon_us.feed_refresh import Source
from pycon_us.layout import use_layout
from pycon_us.locations import TAB_ROOTS, is_top_view, parent_of
from pycon_us.memory import ViewMemory
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import THEME
from pycon_us.services.storage import Storage
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.modals import use_modals_close_on_route_change
from pycon_us.ui.navigation import (
    TABS,
    Rail,
    Retap,
    Select,
    navigation_bar,
    tagged_icon,
)
from pycon_us.ui.semantics import merged
from pycon_us.ui.time_gutter import GutterProbe

logger = logging.getLogger(__name__)


def AppScaffold(
    *,
    title: str,
    body: ft.Control,
    actions: list[ft.Control] | None = None,
    on_retap: Retap | None = None,
    fab: ft.FloatingActionButton | None = None,
    unknown: bool = False,
    still_bar: bool = False,
) -> ft.View:
    """Return a screen's View: the app bar, the bottom bar, the Back rules and the body.

    A plain builder that calls hooks, so a screen calls it exactly once per render, in
    every branch (hooks are unconditional, D-70). It records the top View's route for
    the start route (D-143), places the body in ``Shown``, which logs D-112's content
    line (D-165), and puts ``GutterProbe`` under it, which tells the lists whether a
    slot's time fits beside its rows (D-216). It also makes every route change, a
    warm deep link's included, close the open dialogs and sheets first
    (``ui.modals``, D-291).

    On a tab root the View gets the bottom bar (D-144), with a 1 dp line above it in
    high contrast, where the bar is the page's own colour (THEME-06), or from 600 dp the
    rail beside the body (D-277); pushed Views get the back arrow instead (D-10). A
    root's body is in the same place in both, so a rotation or a resize swaps the bar
    and the rail without rebuilding it: its scroll, day and tabs stay (D-18). Back on a
    root other than Now goes to Now, and Back on Now is left to the system, which leaves
    the app (D-17, D-142). Back on a pushed View closes a dialog, a picker, a sheet or a
    menu open over it, and only then pops the View (D-208). An unknown location's View
    (``unknown``) is a one-View stack like a root but with the back arrow, and Back
    there goes to Now too (D-270).

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
        on_retap: A tab root's action when its active tab is tapped again, on the
            bar or the rail, usually the one ``ui.navigation.use_scroll_to_top()``
            returns; ignored on pushed Views, which have neither.
        fab: The screen's floating action button, if any: the Schedule's "Now"
            (ux.md §5.2). The body leaves room for it at its end.
        unknown: The View of a location no route has (``routes.NotFound``): its
            arrow, the Back key and the predictive gesture go to Now, as a root's
            Back does, and it is never where a new session returns (D-143, D-270).
        still_bar: Keep the app bar's colour whatever scrolls in the body: for a
            screen whose page never scrolls under the bar, only a box inside it, such
            as the floor viewer's label card. Flutter's ``AppBar`` takes any scroll
            in the body at depth 0 for the page's, and Flet has no
            ``notification_predicate`` to say otherwise (F297, D-447).

    Returns:
        The View for this route level.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    wide = use_layout().wide  # the rail rather than the bar (D-277)
    tokens = use_tokens()
    is_root = view_path in TAB_ROOTS
    # One-View stacks whose Back goes to Now: the other roots, and an unknown
    # location, which a cold link can open alone (D-142, D-270).
    back_to_now = (is_root and view_path != "/now") or unknown
    if is_top_view(page.route, view_path) and not unknown:
        svc.memory.last_location = page.route  # where a new session returns (D-143)
    use_modals_close_on_route_change()  # a link never lands under a dialog (D-291)

    @report_errors
    def go_back() -> None:
        # /search returns to its opener, any other View one level up (D-19); an
        # unknown location has no level above it, so Now (D-270).
        page.navigate(
            "/now" if unknown else parent_of(view_path, svc.memory.search_base)
        )

    @report_errors
    async def leave_for_now(e: ft.Event[ft.View]) -> None:
        page.navigate("/now")
        await e.control.confirm_pop(False)  # this View stays; Now replaces the root

    @report_errors
    async def let_pop(e: ft.Event[ft.View]) -> None:
        # Flet asks only when can_pop refuses a pop, which a pushed View never does.
        await e.control.confirm_pop(True)

    @report_errors
    async def switch_tab(index: int) -> None:
        # The bar and the rail report the active destination too, so a re-tap lands
        # here (S4, F95).
        root = TAB_ROOTS[index]
        if root != view_path:
            page.navigate(root)  # roots share one View key: a swap, not a push (D-142)
        elif on_retap is not None:
            await on_retap()

    # Merged, so the tooltip names the arrow's own node (F55, D-234).
    back_arrow = merged(
        ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back)
    )
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
    # Now keeps none: Back there is left to the system, which exits (D-142).
    on_confirm_pop: ft.ControlEventHandler[ft.View] | None = None
    if back_to_now:
        on_confirm_pop = leave_for_now
    elif not is_root:
        # A handler, though the View can always pop: with one, Flet leaves a system pop
        # (the Android Back, VoiceOver's escape on iOS) to Flutter's Navigator, which
        # pops the topmost route, the dialog when one is open; without one, Flet pops
        # this View itself, and the dialog with it (F46).
        on_confirm_pop = let_pop
    return ft.View(
        # Roots share a key, and an unknown location takes it too, so Now replaces
        # either without a transition (D-142, D-270).
        route="/" if is_root or unknown else view_path,
        padding=0,
        appbar=ft.AppBar(
            title=title_control,
            center_title=False,  # as the theme says; iOS would centre it (D-10)
            # Flutter would imply the iOS chevron on iOS; the Material arrow instead.
            automatically_imply_leading=False,
            leading=None if is_root else back_arrow,
            actions=actions or [],
            # The surface it has unscrolled, and no scrolled-under elevation, whose
            # surface tint would colour it (F297, D-447).
            bgcolor=ft.Colors.SURFACE if still_bar else None,
            elevation_on_scroll=0 if still_bar else None,
        ),
        # On roots only: on pushed Views the bar moved with the page (D-144). From
        # 600 dp the rail beside the body takes its place (D-277).
        navigation_bar=(
            navigation_bar(view_path, switch_tab) if is_root and not wide else None
        ),
        floating_action_button=fab,
        can_pop=not back_to_now,
        on_confirm_pop=on_confirm_pop,
        # Under the body, 0 dp high: the probe takes no space, and with no spacing
        # between them the body keeps all of it (D-216).
        spacing=0,
        controls=[
            # In HC the bar keeps the page's colour when a list scrolls under it, its
            # surface_container being surface: the line is its edge (D-306). Both
            # lines keep their slots, hidden outside HC: a line added before the body
            # would shift it, and Flet would remount it, scroll and all (D-18).
            bar_divider(visible=tokens.high_contrast),
            ft.SafeArea(
                expand=True,
                content=beside_rail(view_path, switch_tab, wide, Shown(body))
                if is_root
                else Shown(body),
            ),
            GutterProbe(),
            # The line sits on the bar, which the rail replaces from 600 dp (D-277).
            bar_divider(visible=is_root and tokens.high_contrast and not wide),
        ],
    )


def beside_rail(
    root: str, on_select: Select, wide: bool, shown: ft.Control
) -> ft.Control:
    """Return a tab root's body beside its rail, which shows only when ``wide``.

    The rail stays in the tree, hidden, under 600 dp: the body keeps its place, so
    crossing 600 dp rebuilds neither it nor the screen's components and Flutter's
    state under it, such as a list's scroll (D-18, D-277). Under 600 dp the hidden
    rail is no widget at all (Flet's Dart side leaves out a control that is not
    ``visible``), and the body fills the row as it filled the ``SafeArea``: the phone
    layout is the same, pixel for pixel. The row stretches its children to its height:
    the rail needs a bounded one, and the body had the ``SafeArea``'s.

    Args:
        root: The tab root, one of ``TAB_ROOTS``.
        on_select: The rail's tap handler, the bar's too.
        wide: Whether the window is 600 dp wide or wider (``Layout.wide``).
        shown: The screen's body in its ``Shown``; it has ``expand=True``.
    """
    return ft.Row(
        [Rail(root, on_select, wide), shown],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def bar_divider(visible: bool) -> ft.Control:
    """Return the 1 dp line that separates a bar from the page in HC (THEME-06, D-306).

    High contrast has one surface, so the ``NavigationBar`` and the ``AppBar``, even
    with a list scrolled under it, are the page's colour; a line in ``outline`` draws
    the edge that a tint draws elsewhere. Neither Material bar has a border of its own
    (Flet's ``NavigationBar.border`` is the Cupertino bar's, and an ``AppBar`` shape
    would draw all four sides), so the line opens the View's body, right under the app
    bar, and closes a tab root's, right above the bottom bar: the ``Scaffold`` gives
    the body no inset under an app bar, nor above a bottom bar.

    A hidden line is no widget at all (Flet's Dart side leaves it out), so outside HC
    the layout is the same, pixel for pixel; it stays in the View's controls so that a
    contrast change keeps the body in its place, and its state with it (D-18).

    Args:
        visible: Whether the line shows: in HC, where the bar needs an edge.
    """
    return ft.Divider(height=1, thickness=1, color=ft.Colors.OUTLINE, visible=visible)


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


def search_button(memory: ViewMemory, scope: str) -> ft.Control:
    """Return the app bar action that opens the global search with a preset scope (D-19).

    It records the opener's location, query included, so Back from search returns
    there, and clears the last query, so each search starts empty (D-193). A deep
    link to search has no button: ``screens.search.record_opening()`` records the
    same from the last location as the Search View mounts (D-291).

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

    # Merged, so the tooltip names the button's own node (F55, D-234). The icon carries
    # the identifier UI flows tap it by, merged into that node too (D-252).
    return merged(
        ft.IconButton(
            tagged_icon(ft.Icons.SEARCH, "app.search"),
            tooltip="Search",
            on_click=open_search,
        )
    )


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
