"""The tab roots' bottom bar and rail, and what a re-tap of the active tab does.

``AppScaffold`` puts ``navigation_bar()`` on tab roots only (D-144): on pushed Views the
bar moved with the page on iOS and doubled on Android (S4), so they show the back arrow
instead. From 600 dp wide the roots show ``navigation_rail()`` beside the body instead
(D-09, D-277), with the same destinations. They are fixed and the same for every user
(D-13). Tapping another destination shows that root; tapping the active one runs the
root's re-tap action, which ``use_scroll_to_top()`` provides for a root's list.
"""

from collections.abc import Awaitable, Callable
from typing import NamedTuple

import flet as ft

from pycon_us.locations import TAB_ROOTS
from pycon_us.prefs import use_prefs
from pycon_us.services.errors import report_errors


class Tab(NamedTuple):
    """A destination of the bottom bar (D-13, ux.md §2.1)."""

    root: str
    label: str
    icon: ft.IconData
    selected_icon: ft.IconData

    @property
    def key(self) -> str:
        """The tab's name in semantics identifiers: ``now`` … ``my_schedule`` (section M)."""
        return self.root.strip("/").replace("-", "_")

    @property
    def identifier(self) -> str:
        """The semantics identifier UI tests find it by: ``app.nav.<tab>`` (section M)."""
        return "app.nav." + self.key

    @property
    def title_identifier(self) -> str:
        """The identifier of its root's app-bar title: ``<tab>.title`` (section M).

        UI flows find it to know which root is on screen; a ``Finder`` only counts
        matches, so the title's text alone would not tell the root from its tab label.
        """
        return self.key + ".title"


TABS = (
    Tab("/now", "Now", ft.Icons.SENSORS_OUTLINED, ft.Icons.SENSORS),
    Tab(
        "/schedule",
        "Schedule",
        ft.Icons.CALENDAR_MONTH_OUTLINED,
        ft.Icons.CALENDAR_MONTH,
    ),
    Tab("/my-schedule", "My schedule", ft.Icons.STAR_BORDER, ft.Icons.STAR),
    Tab("/map", "Map", ft.Icons.MAP_OUTLINED, ft.Icons.MAP),
    Tab("/more", "More", ft.Icons.MORE_HORIZ, ft.Icons.MORE_HORIZ),
)
"""The bar's five destinations in ``TAB_ROOTS``' order, the same for every user (D-13).

Outlined when unselected, filled when selected (D-27); More has no filled form.
"""

RETAP_SCROLL_MS = 300
"""How long a re-tap's scroll to the top takes: an M3 medium duration (D-34)."""

RAIL_WIDTH = 80
"""The rail's width in dp at the default text size, M3's; at large text it widens with
its labels, which Flutter does not clamp as it does the bar's (F95, D-277)."""

RAIL_FADE = 40
"""How tall the fade over a short rail's bottom edge is, in dp, and the empty space
under its last destination that keeps that one clear of the fade at the end of a
scroll (D-309)."""

RAIL_FIT_DP = 8 + 5 * 64 - 8
"""The shortest rail whose five labelled destinations all show, in dp, at the default
text size: Flutter's 8 dp spacer, then 64 dp each, the last 16 its label's line,
whose lower half holds no ink for "More" (D-309). A shorter rail cuts More and fades.
"""

type Measured = Callable[[ft.LayoutSizeChangeEvent[ft.LayoutControl]], None]
"""What hears the rail's laid-out size: ``Rail``'s check against ``RAIL_FIT_DP``."""

type Retap = Callable[[], Awaitable[None]]
"""What a root does when its active tab is tapped again: scroll to the top (D-144)."""

type Select = Callable[[int], Awaitable[None]]
"""What a tap on a destination does, given its index in ``TABS``: the bar and the rail
report the active destination too (S4, F95), so this is also a re-tap."""


def navigation_bar(root: str, on_select: Select) -> ft.NavigationBar:
    """Return the bottom bar of a tab root, with that root's destination selected.

    Material, never adaptive, labels always shown (D-10, D-13). A destination has no
    ``Semantics`` of its own, so each icon carries the tab's identifier in an
    unlabelled ``Semantics``, which Flutter merges into the destination's node
    (D-166).

    Args:
        root: The tab root the bar sits on, one of ``TAB_ROOTS``.
        on_select: Called with the tapped destination's index, the active one's too.
    """

    @report_errors
    async def changed(e: ft.Event[ft.NavigationBar]) -> None:
        await on_select(e.control.selected_index)

    return ft.NavigationBar(
        selected_index=TAB_ROOTS.index(root),
        label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        destinations=[
            ft.NavigationBarDestination(
                label=tab.label,
                icon=tagged_icon(tab.icon, tab.identifier),
                selected_icon=tagged_icon(tab.selected_icon, tab.identifier),
            )
            for tab in TABS
        ],
        on_change=changed,
    )


@ft.component
def Rail(root: str, on_select: Select, visible: bool) -> ft.Control:
    """The rail of a tab root, with a fade over its bottom edge when it is short (D-309).

    It measures its own height (``on_size_change``, F51: at mount, after a rotation
    and after a text-size change) and fades its edge only when that is under
    ``RAIL_FIT_DP``, as on an Android phone in landscape (about 303 dp); where the
    destinations show, as on a tablet or an iPhone 17 in landscape (about 325 dp), it
    shows them as D-277 does, with no fade over the last label.

    Args:
        root: The tab root the rail sits on, one of ``TAB_ROOTS``.
        on_select: Called with the tapped destination's index, the active one's too.
        visible: Whether it shows: from ``WIDE_DP`` (``Layout.wide``).
    """
    short, set_short = ft.use_state(False)

    @report_errors
    def measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        set_short(e.height < RAIL_FIT_DP)  # the same value re-renders nothing

    return navigation_rail(
        root, on_select, visible=visible, short=short, on_size_change=measured
    )


def navigation_rail(
    root: str,
    on_select: Select,
    *,
    visible: bool,
    short: bool = False,
    on_size_change: Measured | None = None,
) -> ft.Stack:
    """Return the rail of a tab root, with that root's destination selected (D-277).

    The bar's destinations and labels, as M3 lays a rail out: every label shown, the
    destinations at the top, ``RAIL_WIDTH`` wide. A ``NavigationRail`` has no adaptive
    form (D-10). It scrolls when the destinations are taller than the space beside
    the body, as on a phone in landscape, so each one stays reachable; when it is
    ``short``, a fade over its bottom edge, ``rail_fade()``, is the sign that it does,
    and an empty ``trailing`` as tall lets the last destination scroll clear of it
    (D-309).

    Its icons carry no ``app.nav.<tab>`` identifier, unlike the bar's (F95): an
    identifier makes its ``Semantics`` a node of its own, which only the bar's
    ``MergeSemantics`` folds into the destination, and Flet's ``Semantics`` always
    states ``enabled`` (U34), so in the rail that node is a second, empty TalkBack
    stop in each destination. UI flows find a rail destination by its name,
    "Schedule, Tab 2 of 5", until Flet gives the destination an identifier (#163).

    Args:
        root: The tab root the rail sits on, one of ``TAB_ROOTS``.
        on_select: Called with the tapped destination's index, the active one's too.
        visible: Whether it shows: from ``WIDE_DP`` (``Layout.wide``). A hidden rail
            keeps its place in the View's tree, so the body beside it is never
            rebuilt when the window crosses ``WIDE_DP`` (D-18).
        short: Whether the rail is shorter than ``RAIL_FIT_DP``: the fade shows.
        on_size_change: Hears the rail's laid-out size, ``Rail``'s measurement.

    Returns:
        A ``Stack`` of the ``NavigationRail`` and its fade.
    """

    @report_errors
    async def changed(e: ft.Event[ft.NavigationRail]) -> None:
        if e.control.selected_index is not None:  # Flutter sets it before the event
            await on_select(e.control.selected_index)

    rail = ft.NavigationRail(
        selected_index=TAB_ROOTS.index(root),
        label_type=ft.NavigationRailLabelType.ALL,
        group_alignment=-1,
        min_width=RAIL_WIDTH,
        scrollable=True,
        destinations=[
            ft.NavigationRailDestination(
                label=tab.label, icon=tab.icon, selected_icon=tab.selected_icon
            )
            for tab in TABS
        ],
        # Scrolls with the destinations: at the end of a scroll, More sits above
        # the fade rather than under it.
        trailing=ft.Container(height=RAIL_FADE) if short else None,
        on_change=changed,
    )
    fade = rail_fade()
    fade.visible = short
    return ft.Stack([rail, fade], visible=visible, on_size_change=on_size_change)


def rail_fade() -> ft.Container:
    """Return the fade over the rail's bottom edge: the sign that the rail scrolls.

    On an Android phone in landscape the destinations need 328 dp and the rail has
    about 303, so More is cut at the bottom edge; fading that edge into the rail's colour is
    the usual sign of more below (D-309). It goes from clear to ``surface``, the
    rail's own Material colour, so it matches in every theme, high contrast included.
    It takes no taps and has no semantics, so a tap or TalkBack reaches the
    destination under it.
    """
    return ft.Container(
        left=0,
        right=0,
        bottom=0,
        height=RAIL_FADE,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[ft.Colors.with_opacity(0, ft.Colors.SURFACE), ft.Colors.SURFACE],
        ),
        ignore_interactions=True,
    )


def tagged_icon(icon: ft.IconData, identifier: str) -> ft.Control:
    """Return a decorative icon that gives its enclosing node a semantics identifier.

    Args:
        icon: The icon; its size and colour come from the bar's icon theme.
        identifier: The identifier, e.g. ``app.nav.schedule``.
    """
    return ft.Semantics(identifier=identifier, content=ft.Icon(icon))


def use_scroll_to_top() -> tuple[ft.Ref[ft.ListView], Retap]:
    """Return a ref for a tab root's list and the re-tap action that scrolls it up.

    A plain function that calls hooks, so a root calls it exactly once per render
    (D-70). The scroll animates over ``RETAP_SCROLL_MS``, and jumps when the OS asks
    for reduced motion (D-34). It is the user's own tap, so it does not break "screens
    never move by themselves" (D-18).

    Returns:
        The ref to pass as the list's ``ref``, and the action to pass to
        ``AppScaffold(on_retap=...)``.
    """
    prefs = use_prefs()
    # One ref for the root's lifetime. It stays live although Ref.current is weak:
    # each render's list re-points it, and takes over the mounted one (F38).
    list_ref = ft.use_memo(ft.Ref[ft.ListView], [])

    @report_errors
    async def scroll_to_top() -> None:
        if list_ref.current is not None:  # None until the list has been built
            duration = prefs.motion_ms(RETAP_SCROLL_MS)
            await list_ref.current.scroll_to(offset=0, duration=duration)

    return list_ref, scroll_to_top
