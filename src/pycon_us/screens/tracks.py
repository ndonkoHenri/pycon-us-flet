"""Tracks & session types (``/more/tracks``): one hub for the tracks and their legend.

It answers "what is a charla?" and "show me the charlas" in one place (SCHED-21, EVT-04,
SHELL-10): Ionic's nine Presentations links and its static Session Types page become one
list. Each row is a track of the year's registry (``conference.toml``, D-45): a circle in
the track's badge colours holding its icon, so the hub is also the key to the badges'
colours; its plural name; its legend line; its badge as the schedule shows it, "New
track" when it is new this year; and how many sessions it has, counted as its page lists
them (posters one by one, SCHED-22; the Keynotes page's panels too, D-217). A tap pushes
``/more/tracks/<slug>``: the track's page (``screens/track.py``), or, for the keynotes,
the lightning talks and the open spaces, the page of their own that More opens too,
which the route table puts at that slug under the hub (``year_tracks.HUB_PAGES``,
D-207), so Back returns here.

The rows sit under the registry's groups: Presentations, Hands-on and Community. Breaks
and notices (the ``logistics`` group) are not a kind of session to choose, so they are
left out, and so is a track without sessions in the current feed, which would open an
empty page. The sprints are not a track of the feed, which has no sessions for them
(D-126), but they are a way to take part, so Community ends with a Sprints row, built
like the others, that pushes the Sprints page under the hub (``/more/tracks/sprints``,
EVT-05). Without data the page loads and fails as the Speakers list does (ux.md §4.1).
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import cast

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.models import ConferenceData
from pycon_us.core.rooms import session_count
from pycon_us.core.timefmt import date_range_label
from pycon_us.core.timeline import keynote_sessions, track_sessions
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.theme_badges import BadgeColors
from pycon_us.ui.badges import NEW_TRACK, TrackBadge
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.widths import LIST, sides, use_margin
from pycon_us.year_tracks import HUB_PAGES, Track

SCREEN = "tracks"
"""The screen's name in its semantics identifiers (decisions §M)."""

GROUP_TITLES = {
    "talks": "Presentations",
    "hands-on": "Hands-on",
    "community": "Community",
}
"""The hub's sections: the registry's groups that hold session types, in order."""

ICON_CIRCLE = 40
"""The diameter of a row's tonal circle, in dp (ux.md §5.10)."""

SPRINTS = "/more/tracks/sprints"
"""The Sprints page under the hub, which the hub's Sprints row pushes (EVT-05, D-207)."""

SPRINTS_LEGEND = "Two days of coding on open-source projects, after the talks"
"""The Sprints row's legend line: what the sprints are, as a track's legend says."""


@dataclass(frozen=True)
class HubEntry:
    """One row of the hub: a track and how many sessions its page lists.

    Attributes:
        track: The registry's entry.
        count: Its sessions, as ``track_sessions()`` lists them: every poster, not
            the Posters row.
    """

    track: Track
    count: int


def track_count(
    data: ConferenceData, key: str, keynote_ids: Collection[str] = ()
) -> int:
    """Return how many sessions track ``key``'s page lists (SCHED-22).

    The keynotes' page lists the panels the year data names too (D-217).

    Args:
        data: The processed feed.
        key: A track key.
        keynote_ids: The sessions of the year's keynote data (``Content.keynotes``).
    """
    if key == HUB_PAGES["keynotes"]:
        return len(keynote_sessions(data, key, keynote_ids))
    return sum(len(day.sessions) for day in track_sessions(data, key))


def hub_groups(
    info: ConferenceInfo, data: ConferenceData, keynote_ids: Collection[str] = ()
) -> tuple[tuple[str, tuple[HubEntry, ...]], ...]:
    """Return the hub's sections: a title and its tracks, each with its count.

    The registry's order within a group; a track without sessions is left out, and a
    section without tracks too.

    Args:
        info: The year's facts, with the track registry.
        data: The processed feed.
        keynote_ids: The sessions of the year's keynote data, which the Keynotes
            page lists with the keynotes' track.
    """
    groups: list[tuple[str, tuple[HubEntry, ...]]] = []
    for group, title in GROUP_TITLES.items():
        entries = tuple(
            HubEntry(track, count)
            for track in info.tracks
            if track.group == group
            and (count := track_count(data, track.key, keynote_ids))
        )
        if entries:
            groups.append((title, entries))
    return tuple(groups)


def hub_phrase(entry: HubEntry) -> str:
    """Return what a screen reader says for a hub row: one phrase (D-33).

    "Charlas. Talks given in Spanish. Charla, 16 sessions.", in the order the row
    shows them, with "New track" after the badge when the track is new. A badge that
    says the name again ("Lightning talks") is not read twice.

    Args:
        entry: The row's track and count.
    """
    track = entry.track
    marks = [
        *([track.short] if track.short.casefold() != track.plural.casefold() else []),
        *([NEW_TRACK] if track.new else []),
        session_count(entry.count),
    ]
    return f"{track.plural}. {track.legend}. {', '.join(marks)}."


def sprints_marks(info: ConferenceInfo, projects: int) -> tuple[str, str]:
    """Return the Sprints row's last line as shown and as spoken.

    Its days from the year's data and how many projects the feed lists: "May 18–19 ·
    24 projects", read "May 18 to 19, 24 projects". Either part alone when the other is
    missing; empty for neither.

    Args:
        info: The year's facts: the sprint days (``first_sprint_day`` to ``last_day``).
        projects: How many sprint projects the feed lists.
    """
    shown: list[str] = []
    spoken: list[str] = []
    if (first := info.first_sprint_day) is not None:
        days = date_range_label(first, info.last_day)
        shown.append(days)
        spoken.append(days.replace("\N{EN DASH}", " to "))
    if projects:
        count = f"{projects} project" + ("" if projects == 1 else "s")
        shown.append(count)
        spoken.append(count)
    return " · ".join(shown), ", ".join(spoken)


@ft.component
def Tracks() -> ft.View:
    """The Tracks hub: the year's tracks by group, each pushing its page."""
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    tokens = use_tokens()
    info = svc.year.conference
    data = conference.data
    # Once per feed version: counting walks every track's sessions.
    keynote_ids = [k.session_id for k in svc.year.content.keynotes]
    groups = ft.use_memo(
        lambda: hub_groups(info, data, keynote_ids) if data else (),
        [conference.version],
    )

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    items: list[ft.Control]
    if data is None and conference.problem is None:
        items = [SkeletonList(label="Loading tracks")]  # the first fetch runs (NEW-03)
    elif data is None:
        items = [
            EmptyState(
                "Can't load the tracks",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,  # in place, so focus stays (D-182)
                identifier=f"{SCREEN}.no_data",
            )
        ]
    elif not groups:
        items = [
            EmptyState(
                "No sessions announced yet",
                icon=ft.Icons.SELL_OUTLINED,
                # No button: the app refreshes the feed on its own (D-175).
                body="Tracks show here as soon as the programme is out.",
                identifier=f"{SCREEN}.none",
            )
        ]
    else:
        items = []
        for title, entries in groups:
            items.append(_heading(title))
            items.extend(hub_row(entry, tokens) for entry in entries)
        if info.first_sprint_day is not None or data.sprints:
            # The sprints end the Community section, which may have no track this year.
            if groups[-1][0] != GROUP_TITLES["community"]:
                items.append(_heading(GROUP_TITLES["community"]))
            items.append(sprints_row(info, len(data.sprints), tokens))
    return AppScaffold(
        title="Tracks & session types",
        body=ft.ListView(items, expand=True, padding=sides(margin)),
    )


def _heading(title: str) -> ft.Control:
    """A section's level-2 heading, a node of its own: not read with the row under it."""
    return ft.Semantics(container=True, content=SectionHeader(title, level=2))


def hub_row(entry: HubEntry, tokens: Tokens) -> ft.Control:
    """Return one track of the hub, pushing its page.

    Its circle in the track's badge colours, its plural name and legend, then its
    badge, "New track" when it is new, and its count (``hub_tile()``).

    Args:
        entry: The track and its count.
        tokens: The scheme's tokens, for the track's badge colours (D-150).
    """
    track = entry.track
    colors = tokens.track_badge(track.key)
    marks: list[ft.Control] = [TrackBadge(track.short, colors)]
    if track.new:
        marks.append(TrackBadge(NEW_TRACK, tokens.new_track))
    marks.append(_supporting(session_count(entry.count)))
    return hub_tile(
        circle=track_circle(track, colors),
        title=track.plural,
        legend=track.legend,
        marks=marks,
        phrase=hub_phrase(entry),
        identifier=f"{SCREEN}.track.{track.slug}",
        target=f"/more/tracks/{track.slug}",  # a track's page or its own (D-207)
    )


def sprints_row(info: ConferenceInfo, projects: int, tokens: Tokens) -> ft.Control:
    """Return the hub's Sprints row, pushing the Sprints page (EVT-05).

    Built as a track's row, with the sprints' icon (ux.md §3.7) in a neutral circle,
    since they have no badge colours to be the key to; its last line says when they
    are and how many projects the feed lists. In high contrast the circle is outlined
    in ink, as the unknown track's is (D-306).

    Args:
        info: The year's facts: the sprint days.
        projects: How many sprint projects the feed lists.
        tokens: The scheme's tokens: ``high_contrast`` outlines the circle.
    """
    shown, spoken = sprints_marks(info, projects)
    neutral = BadgeColors(
        text=ft.Colors.ON_SURFACE_VARIANT, fill=ft.Colors.SURFACE_CONTAINER_HIGHEST
    )
    return hub_tile(
        circle=_circle(
            ft.Icons.ROCKET_LAUNCH_OUTLINED,
            tokens.unknown_track if tokens.high_contrast else neutral,
        ),
        title="Sprints",
        legend=SPRINTS_LEGEND,
        marks=[_supporting(shown)] if shown else [],
        phrase=f"Sprints. {SPRINTS_LEGEND}." + (f" {spoken}." if spoken else ""),
        identifier=f"{SCREEN}.sprints",
        target=SPRINTS,
    )


def hub_tile(
    *,
    circle: ft.Control,
    title: str,
    legend: str,
    marks: list[ft.Control],
    phrase: str,
    identifier: str,
    target: str,
) -> ft.Control:
    """Return a row of the hub: a circle, a name, a legend and marks, pushing a page.

    Built like a speaker row (D-189) rather than a ``ListTile``, so that it reads as
    one phrase, a button. Nothing has a fixed height but the circle, so it grows with
    the text; the circle and the chevron stay beside the name at any text size.

    Args:
        circle: The row's 40 dp circle (``track_circle()``).
        title: The name, ``TITLE_MEDIUM``.
        legend: One line on what it is, in the variant colour.
        marks: The last line's pills and words, in one wrapping row; none for no line.
        phrase: What a screen reader says for the whole row.
        identifier: The row's semantics identifier, ``tracks.<element>[.<key>]``.
        target: The page a tap pushes.
    """
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(target)

    lines: list[ft.Control] = [
        ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
        _supporting(legend),
    ]
    if marks:
        # The marks in one wrapping row, spaced as a badge row (ux.md §3.6) and
        # centred on the pills: at large text the count moves under the badges whole.
        lines.append(
            ft.Container(
                ft.Row(
                    marks,
                    wrap=True,
                    spacing=8,
                    run_spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.only(top=4),
            )
        )
    content = ft.Semantics(
        label=phrase,
        identifier=identifier,
        button=True,  # it opens a page: "…, button" (D-33)
        exclude_semantics=True,  # the phrase replaces the texts
        content=ft.Row(
            [
                circle,
                ft.Column(lines, spacing=2, expand=True),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=ft.Colors.ON_SURFACE_VARIANT),
            ],
            spacing=16,
            # Beside the name at any text size, not the middle of a wrapped legend.
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
    )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            content,
            ink=True,
            on_click=go,
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        )
    )


def _supporting(text: str) -> ft.Text:
    """A row's supporting words, in the variant colour."""
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )


def track_circle(track: Track, colors: BadgeColors) -> ft.Control:
    """Return a track's icon in a 40 dp circle of its badge's colours (ux.md §5.10).

    The fill and the icon take the badge's fill and label colours, a pair that reads
    at 6.4:1 or better (D-174), so the circle is the key to the badges' colours. An
    outlined badge (every one in high contrast) gives an outlined circle (D-306).

    Args:
        track: The track, whose ``icon`` names an ``ft.Icons`` member.
        colors: Its badge colours in the current scheme.
    """
    return _circle(cast(ft.IconData, getattr(ft.Icons, track.icon)), colors)


def _circle(icon: ft.IconData, colors: BadgeColors) -> ft.Control:
    """An icon in a 40 dp circle: the fill and the icon in the given colours.

    Without a fill, the circle is a ring in the icon's colour, the badge's border.
    """
    ring = None if colors.fill else ft.Border.all(colors.border_width, colors.text)
    return ft.Container(
        ft.Icon(icon, color=colors.text, size=24),
        width=ICON_CIRCLE,
        height=ICON_CIRCLE,
        bgcolor=colors.fill,
        border=ring,
        shape=ft.BoxShape.CIRCLE,
        alignment=ft.Alignment.CENTER,
    )
