"""The bottom bar of the tab roots, and what a re-tap of the active tab does.

``AppScaffold`` puts ``navigation_bar()`` on tab roots only (D-144): on pushed Views the
bar moved with the page on iOS and doubled on Android (S4), so they show the back arrow
instead. Its five destinations are fixed and the same for every user (D-13). Tapping
another destination shows that root; tapping the active one runs the root's re-tap
action, which ``use_scroll_to_top()`` provides for a root's list. P2's tablet rail (#30)
joins here, with the same destinations.
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

type Retap = Callable[[], Awaitable[None]]
"""What a root does when its active tab is tapped again: scroll to the top (D-144)."""


def navigation_bar(
    root: str, on_change: Callable[[ft.Event[ft.NavigationBar]], Awaitable[None]]
) -> ft.NavigationBar:
    """Return the bottom bar of a tab root, with that root's destination selected.

    Material, never adaptive, labels always shown (D-10, D-13). A destination has no
    ``Semantics`` of its own, so each icon carries the tab's identifier in an
    unlabelled ``Semantics``, which Flutter merges into the destination's node
    (D-166).

    Args:
        root: The tab root the bar sits on, one of ``TAB_ROOTS``.
        on_change: Called with the tapped destination selected, the active one too.
    """
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
        on_change=on_change,
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
