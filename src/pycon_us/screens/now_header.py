"""Now's status header, its words and the rows outside the conference (ux.md §5.1).

The header says where the conference stands, in the brand's indigo (one of D-28's
identity moments): "Starts in 23 days", "Day 3 of 5 · Friday" with "First up today at
9:00 AM" or "That's a wrap for today", the sprints, then "See you next year".
``season()`` and ``header_copy()`` are pure: they map Now & Next's phase (D-179) and
the conference-local date to the words, so the tests hold them at fixed times;
``StatusHeader`` draws them; ``up_next_when()`` words the next slot's start. Before
and after the sessions, ``key_dates()`` lists the year's dates for the countdown and
``sprints_link()`` opens the sprints, both from ``conference.toml`` (D-45). D-14, D-28.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.agenda import NowNext, Phase
from pycon_us.core.models import ConferenceData
from pycon_us.core.timefmt import (
    date_range_label,
    day_heading,
    day_label,
    local_date,
    time_label,
    today,
    weekday_name,
    zone_note,
)
from pycon_us.core.timeline import Slot
from pycon_us.ui.rows import SUBTITLED_TOP, LinkTile
from pycon_us.ui.scaffold import SectionHeader

GOLD = "#FFD779"
"""The brand's gold, for icons on the indigo only (6.2:1 on ``#3B3EA9``; ux.md §3.1)."""

ICON_SIZE = 32
"""The header's decorative icon, in dp."""


class Season(StrEnum):
    """Which of D-14's seasons Now is in: what its sections show.

    Attributes:
        COUNTDOWN: Before the conference's first day: a countdown and key dates.
        CONFERENCE: Its days with sessions, the evenings and mornings between them
            included, and the morning of the first day before its first start: your
            next session, what is on, what is next.
        SPRINTS: The sprint days, after the last session (the feed has none for them).
        OVER: After the last sprint day.
    """

    COUNTDOWN = "countdown"
    CONFERENCE = "conference"
    SPRINTS = "sprints"
    OVER = "over"


SEASON_ICONS: dict[Season, ft.IconData] = {
    Season.COUNTDOWN: ft.Icons.EVENT_OUTLINED,
    Season.CONFERENCE: ft.Icons.SENSORS,  # the Now tab's own icon
    Season.SPRINTS: ft.Icons.ROCKET_LAUNCH_OUTLINED,  # the sprints' icon (ux.md §3.7)
    Season.OVER: ft.Icons.CELEBRATION_OUTLINED,
}
"""The header's decorative icon in each season, in gold."""


def season(
    phase: Phase, day: date, data: ConferenceData, info: ConferenceInfo
) -> Season:
    """Return the season at a conference-local date and phase.

    Before the first start, the first day's own morning is already the conference:
    the attendee is on their way and wants what is first up. After the last end, the
    rest of that evening is still the last day's ("That's a wrap for today"); the
    sprint days follow, from ``conference.toml`` (D-179 leaves them to Now).

    Args:
        phase: ``now_next().phase``.
        day: The conference-local date (``timefmt.today()``).
        data: The processed feed.
        info: The year's facts.
    """
    if phase is Phase.BEFORE:
        if data.days and day >= data.days[0].date:
            return Season.CONFERENCE
        return Season.COUNTDOWN
    if phase is Phase.AFTER:
        if day <= info.last_talk_day:
            return Season.CONFERENCE
        return Season.SPRINTS if day <= info.last_day else Season.OVER
    return Season.CONFERENCE


@dataclass(frozen=True)
class HeaderCopy:
    """What the status header says.

    Attributes:
        season: The season it speaks of.
        title: The headline: "Day 3 of 5 · Friday", "Starts in 23 days".
        subtitle: The line under it: "First up today at 9:00 AM", "May 13–19 ·
            Long Beach, CA".
        note: "Times are Pacific Time (PDT)" when the device's clock differs (D-35).
    """

    season: Season
    title: str
    subtitle: str
    note: str | None = None


def header_copy(
    now_next: NowNext,
    now: datetime,
    data: ConferenceData,
    info: ConferenceInfo,
    *,
    use_24h: bool,
    device_offset: timedelta | None,
) -> HeaderCopy:
    """Return what the status header says at ``now``.

    Args:
        now_next: ``now_next(data, now)``.
        now: ``clock.now()``.
        data: The processed feed.
        info: The year's facts: dates, zone, venue.
        use_24h: The device's 24-hour setting.
        device_offset: The device's UTC offset at ``now``
            (``now.astimezone().utcoffset()``), for the zone note.
    """
    zone = info.zone
    day = today(now, zone)
    note = zone_note(now, zone, info.time_zone_name, device_offset)
    current = season(now_next.phase, day, data, info)
    match current:
        case Season.COUNTDOWN:
            first = data.days[0].date if data.days else info.first_day
            dates = date_range_label(info.first_day, info.last_day)
            return HeaderCopy(
                current, _countdown((first - day).days), f"{dates} · {info.city}", note
            )
        case Season.SPRINTS:
            subtitle = (
                "The last day of the sprints"
                if day == info.last_day
                else f"The sprints run until {day_heading(info.last_day)}"
            )
            return HeaderCopy(current, f"Sprints · {weekday_name(day)}", subtitle, note)
        case Season.OVER:
            return HeaderCopy(current, "See you next year", "Thanks for coming.", note)
        case Season.CONFERENCE:
            number = sum(1 for d in data.days if d.date <= day)
            title = f"Day {number} of {len(data.days)} · {weekday_name(day)}"
            return HeaderCopy(current, title, _day_line(now_next, info, use_24h), note)


def _countdown(days: int) -> str:
    if days <= 0:
        return "Starts today"
    return "Starts tomorrow" if days == 1 else f"Starts in {days} days"


def _day_line(now_next: NowNext, info: ConferenceInfo, use_24h: bool) -> str:
    """The line under a conference day's title, by where the day stands."""
    match now_next.phase:
        case Phase.BEFORE | Phase.BEFORE_DAY if now_next.up_next is not None:
            first = time_label(now_next.up_next.start, info.zone, use_24h=use_24h)
            return f"First up today at {first}"
        case Phase.DAY:
            return info.venue
        case _:  # after the day's last end: the evening, or the last day's
            return "That's a wrap for today"


def header_phrase(name: str, copy: HeaderCopy) -> str:
    """Return what a screen reader says for the header: one phrase (D-33).

    "PyCon US 2026. Day 3 of 5, Friday. First up today at 9:00 AM." A "·" is read
    as a pause and a range's dash as "to".

    Args:
        name: The conference's name, the header's first line.
        copy: What the header says.
    """
    parts = [name, copy.title, copy.subtitle, copy.note or ""]
    spoken = (p.replace(" · ", ", ").replace("–", " to ") for p in parts if p)
    return " ".join(p if p.endswith(".") else f"{p}." for p in spoken)


def StatusHeader(name: str, copy: HeaderCopy, *, dark: bool) -> ft.Control:
    """Return the status header: an indigo card that says where the conference stands.

    Brand colour at an identity moment (D-28): the indigo ``#3B3EA9`` in both schemes,
    as the light ``primary`` (white text, 8.6:1) and the dark ``primary_container``
    (``#E1E0FF``, 6.7:1); its icon is decorative, in gold. One heading node, the page's
    first (level 1), read as ``header_phrase()``.

    Args:
        name: The conference's name, e.g. "PyCon US 2026".
        copy: What it says.
        dark: The dark scheme is on screen (``Prefs.dark``).
    """
    fill = ft.Colors.PRIMARY_CONTAINER if dark else ft.Colors.PRIMARY
    ink = ft.Colors.ON_PRIMARY_CONTAINER if dark else ft.Colors.ON_PRIMARY
    lines: list[ft.Control] = [
        ft.Text(name, theme_style=ft.TextThemeStyle.TITLE_SMALL, color=ink),
        ft.Text(copy.title, theme_style=ft.TextThemeStyle.HEADLINE_SMALL, color=ink),
        ft.Text(copy.subtitle, theme_style=ft.TextThemeStyle.BODY_LARGE, color=ink),
    ]
    if copy.note:
        lines.append(
            ft.Container(
                ft.Text(copy.note, theme_style=ft.TextThemeStyle.BODY_SMALL, color=ink),
                padding=ft.Padding.only(top=4),
            )
        )
    return ft.Semantics(
        label=header_phrase(name, copy),
        header=True,
        heading_level=1,  # a heading needs its level (F40)
        identifier="now.header",
        container=True,
        exclude_semantics=True,  # the phrase replaces the lines
        content=ft.Container(
            ft.Row(
                [
                    ft.Column(lines, spacing=4, expand=True),
                    ft.Icon(SEASON_ICONS[copy.season], size=ICON_SIZE, color=GOLD),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=fill,
            border_radius=16,  # the Now header's shape (ux.md §3.6)
            padding=20,
            margin=ft.Margin.only(left=16, top=8, right=16, bottom=8),
        ),
    )


def key_dates(info: ConferenceInfo) -> list[ft.Control]:
    """Return the countdown's key dates: the conference, the sprints and the venue.

    From ``conference.toml`` (D-45): the days with tutorials and talks, then the
    sprint days, then where it all happens. Each row is one node, read with its dates
    spoken ("Wed, May 13 to Sun, May 17").

    Args:
        info: The year's facts.
    """
    rows = [SectionHeader("Key dates", level=2)]
    rows.append(
        _fact(
            ft.Icons.EVENT_OUTLINED,
            "Tutorials and talks",
            _days(info.first_day, info.last_talk_day),
        )
    )
    if info.last_day > info.last_talk_day:
        first_sprint = info.last_talk_day + timedelta(days=1)
        rows.append(
            _fact(
                ft.Icons.ROCKET_LAUNCH_OUTLINED,
                "Sprints",
                _days(first_sprint, info.last_day),
            )
        )
    rows.append(_fact(ft.Icons.PLACE_OUTLINED, info.venue, info.city))
    return rows


def _days(first: date, last: date) -> str:
    """'Wed, May 13 – Sun, May 17', or one day."""
    if first == last:
        return day_label(first)
    return f"{day_label(first)} – {day_label(last)}"


def _fact(icon: ft.IconData, title: str, subtitle: str) -> ft.Control:
    """A row of information that opens nothing: an icon, a title, its detail."""
    return ft.MergeSemantics(
        content=ft.ListTile(
            leading=ft.Icon(icon),
            title=title,
            subtitle=ft.Text(subtitle, semantics_label=subtitle.replace("–", "to")),
            # As a LinkTile with a subtitle: the icon beside the title's first line.
            title_alignment=ft.ListTileTitleAlignment.TOP,
            min_vertical_padding=SUBTITLED_TOP,
        )
    )


def up_next_when(
    slot: Slot, now: datetime, info: ConferenceInfo, *, use_24h: bool
) -> str:
    """Return when the next slot starts, for its heading: "2:30 PM", "tomorrow at 7:00 AM".

    A later day is named by its date: "Sat, May 16 at 9:00 AM".

    Args:
        slot: ``NowNext.up_next``.
        now: ``clock.now()``.
        info: The year's facts: the zone.
        use_24h: The device's 24-hour setting.
    """
    start = time_label(slot.start, info.zone, use_24h=use_24h)
    day = local_date(slot.start, info.zone)
    days_away = (day - today(now, info.zone)).days
    if days_away == 0:
        return start
    if days_away == 1:
        return f"tomorrow at {start}"
    return f"{day_label(day)} at {start}"


def sprints_link(info: ConferenceInfo) -> ft.Control:
    """Return the row that opens the Sprints page, for the days the feed has nothing for.

    Args:
        info: The year's facts: the sprint days.
    """
    first = info.last_talk_day + timedelta(days=1)
    return LinkTile(
        "Sprints",
        "/more/sprints",
        icon=ft.Icons.ROCKET_LAUNCH_OUTLINED,
        subtitle=date_range_label(first, info.last_day),
        identifier="now.sprints",
    )
