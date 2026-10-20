"""Sprints (``/more/sprints``): the projects of the development sprints (EVT-05..08).

The Tracks hub opens the same page as its child, ``/more/tracks/sprints``, so Back
returns to the hub (D-207).

The feed lists the projects that sign up for the sprints, the two days of coding after
the talks, which have no sessions (D-126). The page says when they are, from the year's
dates (``ConferenceInfo.first_sprint_day`` to ``last_day``), then shows a card per
project, by name: its logo on a white tile, or its initials when the feed has none or
it cannot load (offline); its name, "by <submitter>"; its description, cut at four lines
with "More" when it is long, which shows the whole text with its links (EVT-05); and
"Project page", which opens the project's site in the in-app browser. The card is
``screens/sprint_card.py``'s.

A filter field pinned above the list narrows it as the user types, as the Speakers
list's does (D-189): every word must be in the project's name, submitter or
description text, accents and case ignored, never in markup (EVT-06, D-46). The menu
opens the year's sprint page and its project form on us.pycon.org (EVT-08).

Long lists stay cheap as the Speakers list does (D-153): the projects are ordered once
per feed version, and each card is a memoised component keyed by project id, so a
keystroke re-renders no card that stays. A refresh is the ``Conference`` store's, which
never wipes the cache (EVT-07, D-145); without data the page loads and fails as the
Speakers list does (ux.md §4.1).
"""

from urllib.parse import urlsplit

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.sprints import filter_projects, projects
from pycon_us.core.timefmt import day_heading, day_range_label
from pycon_us.screens.sprint_card import SCREEN, ProjectCard
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, found_count, use_field_query
from pycon_us.ui.links import open_link
from pycon_us.ui.menus import menu_item, overflow_menu
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.widths import LIST, capped, sides, use_margin

FILTER_HINT = "Filter projects"
"""The filter field's hint, and its name for screen readers, which stays with text in it."""

CLEAR_FILTER = "Clear filter"
"""The label of the two controls that empty the filter: the field's and the no-match state's."""

SUBMIT = "Submit a sprint project"
"""The menu item that opens the year's project form (EVT-08)."""

INTRO = (
    "Two days of coding together on open-source projects, after the talks. Join a "
    "project below, whatever your experience."
)
"""What the sprints are, for someone who has never been to one."""


@ft.component
def Sprints() -> ft.View:
    """The Sprints page: when they are, then a filter field over the project cards."""
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    info = svc.year.conference
    field = use_field_query()
    tokens = use_tokens()
    query = field.value
    data = conference.data
    # Once per feed version: a keystroke re-renders this screen, never re-sorts.
    listed = ft.use_memo(lambda: projects(data) if data else (), [conference.version])

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    @report_errors
    async def submit() -> None:
        await open_link(svc, info.sprint_submit_url)

    pinned: list[ft.Control] = []
    items: list[ft.Control]
    if data is None and conference.problem is None:
        items = [SkeletonList(label="Loading sprint projects")]  # NEW-03
    elif data is None:
        items = [
            EmptyState(
                "Can't load the sprints",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,  # in place, so focus stays (D-182)
                identifier=f"{SCREEN}.no_data",
            )
        ]
    elif not listed:
        # Nothing to filter, so no field; the form is the way out, when the year has one.
        items = [
            *intro(info),
            EmptyState(
                "No sprint projects yet",
                icon=ft.Icons.ROCKET_LAUNCH_OUTLINED,
                body="Projects show here as soon as they sign up.",
                action="Submit a project" if info.sprint_submit_url else None,
                on_action=submit if info.sprint_submit_url else None,
                identifier=f"{SCREEN}.none",
            ),
        ]
    else:
        found = filter_projects(listed, query)
        pinned = [
            SearchField(
                value=field.value,
                on_change=field.changed,
                on_clear=field.clear,
                ref=field.ref,
                hint=FILTER_HINT,
                label=FILTER_HINT,
                clear_tooltip=CLEAR_FILTER,
                identifier=f"{SCREEN}.filter",
                high_contrast=tokens.high_contrast,
            )
        ]
        if found and found is not listed:  # a filter applies and finds some
            pinned.append(
                found_count(
                    f"{len(found)} project" + ("" if len(found) == 1 else "s"),
                    identifier=f"{SCREEN}.count",
                )
            )
        items = [*intro(info)]
        if found:
            # A node of its own, so it is not read with the first card.
            items.append(
                ft.Semantics(container=True, content=SectionHeader("Projects", level=2))
            )
            items.extend(ProjectCard(sprint) for sprint in found)
        else:
            items.append(
                EmptyState(
                    f"No projects match \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
                    "\N{RIGHT DOUBLE QUOTATION MARK}",
                    icon=ft.Icons.SEARCH_OFF,
                    action=CLEAR_FILTER,
                    on_action=field.clear,  # the focus goes back to the field
                    identifier=f"{SCREEN}.no_match",
                )
            )
    return AppScaffold(
        title="Sprints",
        actions=_menu(info, svc),
        body=ft.Column(
            [
                # The field and its count in a column of their own, so the list keeps
                # its place in the body as they come and go (D-189, D-153).
                capped(
                    ft.Column(
                        pinned,
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    margin,
                ),
                ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
            ],
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def intro(info: ConferenceInfo) -> list[ft.Control]:
    """Return the page's opening: what the sprints are, then their days (EVT-05).

    The days come from the year's data, from the day after the last talk day to the
    last day; a year without sprint days shows none.

    Args:
        info: The year's facts.
    """
    controls: list[ft.Control] = [
        ft.Container(
            ft.Text(
                INTRO,
                theme_style=ft.TextThemeStyle.BODY_LARGE,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            padding=ft.Padding.only(left=16, top=12, right=16),
        )
    ]
    first = info.first_sprint_day
    if first is not None:
        dates = day_range_label(first, info.last_day)
        spoken = (
            day_heading(first)
            if first == info.last_day
            else f"{day_heading(first)} to {day_heading(info.last_day)}"
        )
        controls.append(
            ft.Semantics(
                label=f"Sprints: {spoken}",
                identifier=f"{SCREEN}.dates",
                exclude_semantics=True,  # "Mon, May 18 – Tue, May 19" said in words
                content=ft.Container(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.EVENT_OUTLINED, size=20),
                            ft.Text(
                                dates,
                                theme_style=ft.TextThemeStyle.TITLE_SMALL,
                                expand=True,
                            ),
                        ],
                        spacing=12,
                    ),
                    padding=ft.Padding.only(left=16, top=12, right=16, bottom=4),
                ),
            )
        )
    return controls


def _menu(info: ConferenceInfo, svc: Services) -> list[ft.Control]:
    """The app bar's overflow: the year's sprint page and its project form (EVT-08).

    Each item leaves the app: a link, read "Opens in browser" after its words, as
    session detail's "Open on us.pycon.org" is (D-186), whose label wraps at 200 %
    text (``menu_item()``, F47, D-233). A year without either URL has no item for it,
    and without both no menu (no dead control, ux.md §1).
    """
    links: list[tuple[str, str, str]] = []
    if info.sprints_url:
        host = urlsplit(info.sprints_url).hostname
        links.append((f"Sprint info on {host}", info.sprints_url, "info"))
    if info.sprint_submit_url:
        links.append((SUBMIT, info.sprint_submit_url, "submit"))
    if not links:
        return []

    items = [_menu_item(label, url, key, svc) for label, url, key in links]
    return [overflow_menu(f"{SCREEN}.menu", items)]


def _menu_item(label: str, url: str, key: str, svc: Services) -> ft.PopupMenuItem:
    """One link of the menu, ``sprints.<key>``, read "<label>, Opens in browser"."""

    @report_errors
    async def go() -> None:
        await open_link(svc, url)

    return menu_item(
        ft.Icons.OPEN_IN_NEW, label, go, identifier=f"{SCREEN}.{key}", link=True
    )
