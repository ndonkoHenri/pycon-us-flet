"""Now's quick info buttons: Wi-Fi, Help & safety, Venue & hours (INFO-08, INFO-07, MAP-09).

During the conference these are the pages people need most, and More is two taps away
(ux.md §5.1 item 11). A wrapping row of three ``FilledTonalButton``s pushes each page
over Now, ``/now/wifi``, so Back returns here (D-17). They show in the conference and
sprint seasons only, after the sessions and the Schedule link and before the sponsor
spotlight, so at peak times they never push Now's sessions down (D-338, D-327).
Apart from ``now.py`` so that the screen stays under about 400 lines (D-66, D-190).
"""

import flet as ft

from pycon_us.screens.more import AT_THE_VENUE, MoreEntry
from pycon_us.screens.now_header import Season
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import named

SEASONS = frozenset({Season.CONFERENCE, Season.SPRINTS})
"""The seasons that show the buttons: the days at the venue (D-338)."""

PAGES = ("wifi", "help", "venue")
"""The pages' segments, in the row's order: the password first, the one most asked."""


def entries() -> tuple[MoreEntry, ...]:
    """Return More's At the venue entries in the row's order (``PAGES``).

    The titles and icons stay More's own, so the two never disagree.
    """
    by_segment = {e.location.rsplit("/", 1)[-1]: e for e in AT_THE_VENUE}
    return tuple(by_segment[segment] for segment in PAGES)


def QuickInfo(view_path: str) -> ft.Control:
    """Return the row of quick info buttons, a memoised component.

    Given the same View path, it skips its body (D-153, F34), so Now's minute tick
    never re-renders it.

    Args:
        view_path: Now's View path, which the pages are pushed on.
    """
    return _QuickInfo(view_path)


@ft.memo
@ft.component
def _QuickInfo(view_path: str) -> ft.Control:
    """The body of ``QuickInfo``; it runs only when its View path changes."""
    page = ft.context.page

    def button(entry: MoreEntry) -> ft.Control:
        """One page's button, ``now.quick.<page>`` (D-33)."""
        segment = entry.location.rsplit("/", 1)[-1]

        @report_errors
        def go() -> None:
            page.navigate(f"{view_path.rstrip('/')}/{segment}")

        # Material pads a button's tap target to 48 dp on phones, so a 40 dp tonal
        # button still takes a 48 dp tap (ux.md §9).
        return named(
            f"now.quick.{segment}",
            ft.FilledTonalButton(entry.title, icon=entry.icon, on_click=go),
        )

    return ft.Container(
        # Wrapping, so at 200 % text a button that no longer fits moves down whole.
        ft.Row(
            [button(entry) for entry in entries()],
            wrap=True,
            spacing=8,
            run_spacing=0,  # each button's 48 dp tap target already parts the lines
        ),
        padding=ft.Padding.only(left=16, top=16, right=16),
    )
