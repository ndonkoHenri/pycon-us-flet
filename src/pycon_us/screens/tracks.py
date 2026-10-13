"""Tracks & session types (``/more/tracks``): one hub for the tracks and their legend.

It answers "what is a charla?" and "show me the charlas" in one place (SCHED-21, EVT-04,
SHELL-10): Ionic's nine Presentations links and its static Session Types page become one
list. Each row is a track of the year's registry (``conference.toml``, D-45): a circle in
the track's badge colours holding its icon, so the hub is also the key to the badges'
colours; its plural name; its legend line; its badge as the schedule shows it, "New
track" when it is new this year; and how many sessions it has, counted as its page lists
them (posters one by one, SCHED-22). A tap pushes the track's page,
``/more/tracks/<slug>`` (``screens/track.py``), or, for the lightning talks and the open
spaces, their own page in More (``OWN_PAGES``).

The rows sit under the registry's groups: Presentations, Hands-on and Community. Breaks
and notices (the ``logistics`` group) are not a kind of session to choose, so they are
left out, and so is a track without sessions in the current feed, which would open an
empty page. Without data the page loads and fails as the Speakers list does (ux.md §4.1).
"""

from dataclasses import dataclass
from typing import cast

import flet as ft

from pycon_us.config import ConferenceInfo, Track
from pycon_us.core.models import ConferenceData
from pycon_us.core.rooms import session_count
from pycon_us.core.timeline import track_sessions
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import BadgeColors, Tokens, use_tokens
from pycon_us.ui.badges import NEW_TRACK, TrackBadge
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList

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

OWN_PAGES = {
    "Lightning-talks": "/more/lightning-talks",
    "Open Space": "/more/open-spaces",
}
"""Tracks with a page of their own in More, which their hub row opens instead of the
track page (ux.md §5.10, EVT-01, EVT-03), by track key: the feed's kinds, which do not
change with the year (DATA-14)."""


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


def track_count(data: ConferenceData, key: str) -> int:
    """Return how many sessions track ``key``'s page lists (SCHED-22).

    Args:
        data: The processed feed.
        key: A track key.
    """
    return sum(len(day.sessions) for day in track_sessions(data, key))


def hub_groups(
    info: ConferenceInfo, data: ConferenceData
) -> tuple[tuple[str, tuple[HubEntry, ...]], ...]:
    """Return the hub's sections: a title and its tracks, each with its count.

    The registry's order within a group; a track without sessions is left out, and a
    section without tracks too.

    Args:
        info: The year's facts, with the track registry.
        data: The processed feed.
    """
    groups: list[tuple[str, tuple[HubEntry, ...]]] = []
    for group, title in GROUP_TITLES.items():
        entries = tuple(
            HubEntry(track, count)
            for track in info.tracks
            if track.group == group and (count := track_count(data, track.key))
        )
        if entries:
            groups.append((title, entries))
    return tuple(groups)


def hub_target(track: Track) -> str:
    """Return where a hub row goes: the track's own page, else its track page.

    Args:
        track: The registry's entry.
    """
    return OWN_PAGES.get(track.key, f"/more/tracks/{track.slug}")


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


@ft.component
def Tracks() -> ft.View:
    """The Tracks hub: the year's tracks by group, each pushing its page."""
    svc = use_services()
    conference = use_conference()
    tokens = use_tokens()
    info = svc.year.conference
    data = conference.data
    # Once per feed version: counting walks every track's sessions.
    groups = ft.use_memo(
        lambda: hub_groups(info, data) if data else (), [conference.version]
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
            # A node of its own, so it is not read with the row under it.
            items.append(
                ft.Semantics(container=True, content=SectionHeader(title, level=2))
            )
            items.extend(hub_row(entry, tokens) for entry in entries)
    return AppScaffold(
        title="Tracks & session types", body=ft.ListView(items, expand=True)
    )


def hub_row(entry: HubEntry, tokens: Tokens) -> ft.Control:
    """Return one track of the hub, pushing its page.

    Built like a speaker row (D-189) rather than a ``ListTile``, so that it reads as
    one phrase (``hub_phrase()``), a button. Nothing has a fixed height but the
    circle, so it grows with the text; the circle and the chevron stay beside the
    name at any text size.

    Args:
        entry: The track and its count.
        tokens: The scheme's tokens, for the track's badge colours (D-150).
    """
    page = ft.context.page
    track = entry.track
    colors = tokens.track_badge(track.key)

    @report_errors
    def go() -> None:
        page.navigate(hub_target(track))

    badges = [TrackBadge(track.short, colors)]
    if track.new:
        badges.append(TrackBadge(NEW_TRACK, tokens.new_track))
    count = ft.Text(
        session_count(entry.count),
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    lines = ft.Column(
        [
            ft.Text(track.plural, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
            ft.Text(
                track.legend,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            # The badges and the count in one wrapping row, spaced as a badge row
            # (ux.md §3.6) and centred on the pills: at large text the count moves
            # under the badges whole.
            ft.Container(
                ft.Row(
                    [*badges, count],
                    wrap=True,
                    spacing=8,
                    run_spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.only(top=4),
            ),
        ],
        spacing=2,
        expand=True,
    )
    content = ft.Semantics(
        label=hub_phrase(entry),
        identifier=f"{SCREEN}.track.{track.slug}",
        button=True,  # it opens the track's page: "…, button" (D-33)
        exclude_semantics=True,  # the phrase replaces the texts
        content=ft.Row(
            [
                track_circle(track, colors),
                lines,
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


def track_circle(track: Track, colors: BadgeColors) -> ft.Control:
    """Return a track's icon in a 40 dp circle of its badge's colours (ux.md §5.10).

    The fill and the icon take the badge's fill and label colours, a pair that reads
    at 6.4:1 or better (D-174), so the circle is the key to the badges' colours.

    Args:
        track: The track, whose ``icon`` names an ``ft.Icons`` member.
        colors: Its badge colours in the current scheme.
    """
    return ft.Container(
        ft.Icon(
            cast(ft.IconData, getattr(ft.Icons, track.icon)),
            color=colors.text,
            size=24,
        ),
        width=ICON_CIRCLE,
        height=ICON_CIRCLE,
        bgcolor=colors.fill,
        shape=ft.BoxShape.CIRCLE,
        alignment=ft.Alignment.CENTER,
    )
