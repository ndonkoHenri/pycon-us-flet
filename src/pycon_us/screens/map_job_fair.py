"""The Map's Job fair pane: the plan's card, the year's note, then who is at each table.

One scrolling list (D-254, ux.md §6.3; MAP-04, SPON-10), never a split pane: at the
largest text a viewer over a list leaves the list no room (#331), and a zoom layer in a
page that scrolls fights its pans (MAP-01). So the plan is a card, ``job_fair_card()``,
that pushes the floor viewer at ``…/plan/job-fair`` (no pins), and under it:

- **The note** (``map.toml``'s ``note`` on the ``job-fair`` plan): why the rows and the
  print disagree, a paragraph that wraps with no line limit, only when the year has one.
- **Tables** (a level-2 heading), then a row per sponsor with a table
  (``core.expo.job_fair_tables()``), in natural table order, a shared table's sponsors
  together by name: "T2 · Bloomberg · 15 open roles" (the count only when its listings
  have roles), one node read "Table T2, Bloomberg, 15 open roles", a button that pushes
  the sponsor (``…/sponsor/<slug>``), so Back returns to the pane.

The rows follow the feed, which a refresh can correct during the conference; the image
changes only with a build. Without data the pane loads and fails as Rooms does (ux.md
§4.1), the card kept, since the plan is bundled; a feed without tables says "No job fair
tables yet". The Map (``screens/map.py``) shows it under its tab bar.
"""

import flet as ft

from pycon_us.core.expo import JobFairTable, job_fair_tables
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.ui.location_card import job_fair_card
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.scrolling import SCROLL_EVENT_MS
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.status_strip import StatusStrip
from pycon_us.ui.widths import LIST, sides, use_margin
from pycon_us.year_map import JOB_FAIR_PLAN, MapData

SCREEN = "map"
"""The screen's name in its semantics identifiers (decisions §M)."""

JOB_FAIR = JOB_FAIR_PLAN
"""The pane's slug: its ``?tab=`` value, its list's key and its tab's identifier."""

TABLES = "Tables"
"""The heading over the rows."""


def roles_phrase(count: int) -> str:
    """Return "15 open roles" ("1 open role"), or "" for none.

    Args:
        count: The sponsor's open roles (``JobFairTable.roles``).
    """
    if not count:
        return ""
    return f"{count} open role" if count == 1 else f"{count} open roles"


def table_line(entry: JobFairTable) -> str:
    """Return a row's text: "T2 · Bloomberg · 15 open roles", the count only with roles.

    Args:
        entry: The sponsor at its table.
    """
    parts = (entry.table, entry.sponsor.name, roles_phrase(entry.roles))
    return " · ".join(part for part in parts if part)


def table_phrase(entry: JobFairTable) -> str:
    """Return what a screen reader says of a row: "Table T2, Bloomberg, 15 open roles".

    Args:
        entry: The sponsor at its table.
    """
    parts = (f"Table {entry.table}", entry.sponsor.name, roles_phrase(entry.roles))
    return ", ".join(part for part in parts if part)


@ft.component
def JobFairPane(
    list_ref: ft.Ref[ft.ListView], on_scroll: ft.EventHandler[ft.OnScrollEvent]
) -> ft.Control:
    """The Job fair pane: the plan's card and note, then a row per sponsor at a table.

    Args:
        list_ref: The Map's list ref, which its re-tap scrolls.
        on_scroll: The Map's scroll handler, which remembers where a scroll ended.
    """
    margin = use_margin(LIST)
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    data = conference.data
    rows: list[ft.Control] = []
    if data is None:
        rows.append(StatusStrip())  # its bar shows a retry while there is no feed
    rows.extend(plan_rows(svc.year.map))
    if data is None and conference.problem is None:
        rows.append(SkeletonList("Loading tables"))
    elif data is None:
        rows.append(
            EmptyState(
                "Can't load the tables",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,
                identifier=f"{SCREEN}.job_fair.no_data",
            )
        )
    elif tables := job_fair_tables(data):
        rows.append(SectionHeader(TABLES))
        rows.extend(table_row(entry, view_path) for entry in tables)
    else:
        rows.append(
            EmptyState(
                "No job fair tables yet",
                icon=ft.Icons.WORK_OUTLINE,
                # No button: the app refreshes the feed on its own (D-175).
                body="Who is at each table shows here as soon as the conference "
                "lists it.",
                identifier=f"{SCREEN}.job_fair.empty",
            )
        )
    return ft.ListView(
        rows,
        key=JOB_FAIR,  # its own, so Flutter never reuses another pane's list (F130)
        ref=list_ref,
        expand=True,
        padding=sides(margin, bottom=8),
        scroll_interval=SCROLL_EVENT_MS,
        on_scroll=on_scroll,
    )


def plan_rows(data: MapData) -> list[ft.Control]:
    """Return the pane's head: the job fair plan's card, then the year's note under it.

    The note is a paragraph in ``BODY_MEDIUM`` and ``on_surface_variant`` that wraps
    with no line limit (D-254); a year without one, or without the plan, leaves it out.

    Args:
        data: The year's ``map.toml``.
    """
    card = job_fair_card(data, identifier=f"{SCREEN}.job_fair.location")
    plan = data.plan(JOB_FAIR_PLAN)
    if card is None or plan is None:
        return []
    rows: list[ft.Control] = [
        ft.Container(card, padding=ft.Padding.only(left=16, right=16, top=8))
    ]
    if plan.note:
        rows.append(
            ft.Container(
                ft.Text(
                    plan.note,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.only(left=16, right=16, top=12),
            )
        )
    return rows


def table_row(entry: JobFairTable, view_path: str) -> ft.Control:
    """Return one sponsor's row: its table, its name and its open roles, then a chevron.

    Built as a Sponsors row is, not as a ``ListTile``, so it reads as one phrase that
    says "Table" where the line says "T2" (D-33); 56 dp for one line, it grows with the
    text. Identifier ``map.table.<sponsor slug>``: a shared table has two rows.

    Args:
        entry: The sponsor at its table.
        view_path: The Map's View path, so the sponsor is pushed on top of it.
    """
    target = drill_href(view_path, "sponsor", entry.sponsor.slug)

    @report_errors
    def go() -> None:
        ft.context.page.navigate(target)

    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=table_phrase(entry),
                identifier=f"{SCREEN}.table.{entry.sponsor.slug}",
                button=True,  # it opens the sponsor: "…, button" (D-33)
                exclude_semantics=True,  # the phrase replaces the line
                content=ft.Row(
                    [
                        ft.Text(
                            table_line(entry),
                            theme_style=ft.TextThemeStyle.BODY_LARGE,
                            expand=True,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ink=True,
            on_click=go,
            # 56 dp for a line of 24, as a one-line ListTile; taller as it wraps.
            padding=ft.Padding.symmetric(horizontal=16, vertical=16),
        )
    )
