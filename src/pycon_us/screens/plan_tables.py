"""The job fair's tables on the floor viewer: ``…/plan/job-fair?table=T8`` (#464; MAP-04).

The ``job-fair`` plan is the print, whose logos and the feed disagree at T7, T8, T12 and
T16 (D-254), so a table shows its place on the plan and the feed says who is at it:

- **A tap area per table** of ``map.toml``'s ``[[tables]]``: one positioned
  ``Container`` in ``Semantics(button=True)`` (D-312), read "Table T7, Chainguard, Red
  Hat" (``plan.table.T7``), "Table T13, no sponsor listed", or "Table T7" before the
  feed is there. A tap selects it without moving the camera (until U3): an amber fill
  over the print and an amber outline, the node marked selected. So the plan has no
  double tap, which would delay every tap (D-312).
- **The table's card** under the plan, outside the zoom layer: "Table T7" over a row
  per sponsor the feed puts there, each pushing the sponsor (``plan.table_sponsor.
  <slug>``), or "No sponsor listed at T13"; a table the feed names without a rectangle
  is "Table T21 isn't on the plan yet", with its sponsors.

``table_href()`` is the way in: the Job fair pane's "Show table T8 on the plan" and
sponsor detail's "Job fair table T8". ``screens/plan.py`` holds the selection.
"""

from collections.abc import Callable
from urllib.parse import quote

import flet as ft

from pycon_us.core.expo import job_fair_tables
from pycon_us.core.models import ConferenceData, Sponsor
from pycon_us.locations import drill_href
from pycon_us.services.errors import report_errors
from pycon_us.ui.zoom_geometry import Size
from pycon_us.year_map import JOB_FAIR_PLAN, Table

SCREEN = "plan"
"""The floor viewer's name in its semantics identifiers (decisions §M)."""

TABLE_PARAM = "table"
"""The query option that selects a table: ``…/plan/job-fair?table=T8``."""

AMBER = "#F2C14E"
"""The selected table's amber, the expo's selected booth's (#402), on the print's purple
at well over 3:1 in either theme: the plan is the same image in both."""

FILL_OPACITY = 0.45
"""How much amber covers a selected table: its printed logo still shows."""

OUTLINE_DP = 4


def table_href(view_path: str, number: str) -> str:
    """Return the location that pushes the job fair plan with table ``number`` selected.

    Args:
        view_path: The View to push it on (``ft.use_view_path()``).
        number: The table, as the feed writes it ("T8").

    Returns:
        The location, e.g. ``/map/plan/job-fair?table=T8``.
    """
    plan = drill_href(view_path, "plan", JOB_FAIR_PLAN)
    return f"{plan}?{TABLE_PARAM}={quote(number, safe='')}"


def show_table_label(number: str) -> str:
    """Return the name of a button that shows a table: "Show table T8 on the plan".

    Args:
        number: The table, as the feed writes it.
    """
    return f"Show table {number} on the plan"


def sponsors_at(data: ConferenceData | None, number: str) -> tuple[Sponsor, ...] | None:
    """Return the sponsors the feed puts at table ``number``, by folded name.

    Args:
        data: The processed feed, or None before there is one.
        number: The table ("T7").

    Returns:
        The sponsors, possibly none; None without a feed, which knows nobody.
    """
    if data is None:
        return None
    return tuple(e.sponsor for e in job_fair_tables(data) if e.table == number)


def table_phrase(number: str, sponsors: tuple[Sponsor, ...] | None) -> str:
    """Return what a screen reader says of a table: "Table T7, Chainguard, Red Hat".

    "Table T13, no sponsor listed" when the feed has none; "Table T7" without a feed.

    Args:
        number: The table.
        sponsors: Its sponsors (``sponsors_at()``).
    """
    if sponsors is None:
        return f"Table {number}"
    names = ", ".join(sponsor.name for sponsor in sponsors) or "no sponsor listed"
    return f"Table {number}, {names}"


def table_area(
    table: Table,
    shown: Size,
    sponsors: tuple[Sponsor, ...] | None,
    on_select: Callable[[str], None],
    *,
    selected: bool,
) -> ft.Control:
    """Return a table's tap area, placed on the fitted plan from its ratios.

    Args:
        table: The table.
        shown: The plan's fitted size (``ui.zoom_geometry.fitted()``).
        sponsors: Its sponsors, for its words (``sponsors_at()``).
        on_select: Called with the table's number when it is tapped.
        selected: Whether it is the selected table.
    """
    width, height = shown

    @report_errors
    def tap() -> None:
        on_select(table.number)

    return ft.Container(
        left=table.x * width,
        top=table.y * height,
        width=table.w * width,
        height=table.h * height,
        # content= by name: a positional Semantics(x) is its tooltip (F130).
        content=ft.Semantics(
            content=ft.Container(
                # Unselected, the print shows the table; a transparent fill still
                # takes the taps, as Flet decorates every Container.
                bgcolor=ft.Colors.with_opacity(FILL_OPACITY, AMBER)
                if selected
                else ft.Colors.TRANSPARENT,
                border=ft.Border.all(OUTLINE_DP, AMBER) if selected else None,
                border_radius=4,
                on_click=tap,
            ),
            button=True,
            # Only the selected one says so: False would read "not selected" 20 times.
            selected=True if selected else None,
            label=table_phrase(table.number, sponsors),
            identifier=f"{SCREEN}.table.{table.number}",
        ),
    )


def table_card(
    number: str,
    sponsors: tuple[Sponsor, ...] | None,
    view_path: str,
    *,
    placed: bool,
) -> ft.Control:
    """Return the selected table's card: its name, then who the feed puts there.

    Args:
        number: The table.
        sponsors: Its sponsors (``sponsors_at()``); None without a feed, which shows
            the name alone.
        view_path: The floor viewer's View path, so a sponsor is pushed on top of it.
        placed: Whether the table has a rectangle on the plan; "Table T21 isn't on
            the plan yet" when not.
    """
    title = f"Table {number}" if placed else f"Table {number} isn't on the plan yet"
    lines: list[ft.Control] = [
        ft.Container(
            ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_SMALL),
            padding=ft.Padding.only(left=16, top=12, right=16, bottom=4),
        )
    ]
    if sponsors:
        lines.extend(sponsor_row(sponsor, view_path) for sponsor in sponsors)
    elif sponsors is not None:
        lines.append(
            ft.Container(
                ft.Text(
                    f"No sponsor listed at {number}",
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.only(left=16, right=16, bottom=12),
            )
        )
    card = ft.Card(ft.Column(lines, spacing=0, tight=True), margin=0)
    return ft.Semantics(identifier=f"{SCREEN}.table_card", container=True, content=card)


def sponsor_row(sponsor: Sponsor, view_path: str) -> ft.Control:
    """Return a sponsor's row in the table's card: its name and a chevron, 48 dp.

    One button node, read "Red Hat, sponsor details" (``plan.table_sponsor.<slug>``),
    that pushes ``…/sponsor/<slug>`` on the floor viewer, so Back returns to the plan.

    Args:
        sponsor: A sponsor at the table.
        view_path: The floor viewer's View path.
    """
    target = drill_href(view_path, "sponsor", sponsor.slug)

    @report_errors
    def go() -> None:
        ft.context.page.navigate(target)

    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=f"{sponsor.name}, sponsor details",
                identifier=f"{SCREEN}.table_sponsor.{sponsor.slug}",
                button=True,
                exclude_semantics=True,  # the phrase replaces the line
                content=ft.Row(
                    [
                        ft.Text(
                            sponsor.name,
                            theme_style=ft.TextThemeStyle.BODY_LARGE,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    spacing=16,
                ),
            ),
            ink=True,
            on_click=go,
            # 48 dp for a line of 24; taller as it wraps.
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        )
    )
