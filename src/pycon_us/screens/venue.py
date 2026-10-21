"""Venue & hours (``/more/venue``): is it open now, and how do I get there (MAP-09, MAP-11).

Ionic split the site's HTML into cards and never said what was open. This page renders
at once from bundled year data (D-45, INFO-05), offline, and answers both questions
(D-313):

- **The address card:** the venue's name and address (``conference.toml``'s
  ``address``), with **Directions**, which opens Apple Maps on iOS and the ``geo:``
  handler on Android at the venue's point (``[directions]``, ``directions_url()``),
  and **Copy address** (``copy_text()``, D-263). A launch that fails says "Couldn't
  open the link" (D-182).
- **A card per service** from ``[[venue_hours]]`` (D-282): its name as a level-2
  heading, a status label from ``core/hours.py``'s ``hours_status()`` ("Open now ·
  until 6:00 PM" in ``live``, "Opens 7:30 AM", "Closed today"), an icon and words that
  are read as words and never a chip, since a tap does nothing (ux.md §6.7); where it
  is, its days with today's in bold, and its note. The page re-renders on the minute
  (``use_minute()``), so the labels follow the clock, the Developer fake clock too;
  off-season there are none (``hours_status()`` is None).

Hours are conference time; while the device's zone differs a line says so (D-35,
D-240). A year without ``[[venue_hours]]`` shows the feed's ``venues-hours`` block, and
without that the empty state (``InfoBody``).
"""

import re
from collections.abc import Mapping
from datetime import date, datetime, tzinfo
from urllib.parse import quote

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.hours import HoursStatus, ServiceHours, hours_status
from pycon_us.core.timefmt import (
    day_heading,
    day_label,
    local_date,
    on_screen,
    time_label,
    time_range_label,
    zone_note,
)
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.info_page import GUTTER, InfoBody
from pycon_us.ui.links import OPENS_IN, LinkKind, copy_text, external, open_link
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.ui.status_strip import use_minute
from pycon_us.year_info import Directions

SCREEN = "venue"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "Venue & hours"
"""The page's name: its app bar's title and its More row (ux.md §4.9's spelling)."""

DIRECTIONS = "Directions"
COPY_ADDRESS = "Copy address"
ADDRESS_COPIED = "Address copied"
ADDRESS_NOT_COPIED = "Couldn't copy the address"

NO_VENUE = "No venue details yet"
NO_VENUE_BODY = "Ask at the information desk where things are and when they open."
"""The empty state's way out: no button can bring the hours (ux.md §4.6)."""

STATUS_ICONS = {
    "open": ft.Icons.CHECK_CIRCLE_OUTLINE,
    "later_today": ft.Icons.SCHEDULE,
    "another_day": ft.Icons.EVENT_OUTLINED,
    "closed_today": ft.Icons.DO_NOT_DISTURB_ON_OUTLINED,
}
"""Each status's decorative icon beside its words, outlined (D-27)."""


@ft.component
def Venue() -> ft.View:
    """The Venue & hours page: the address card, then a card per service."""
    svc = use_services()
    tokens = use_tokens()
    use_minute()  # the labels, today's bold and the zone note follow the clock
    page = ft.context.page
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    hours = svc.year.content.venue_hours
    blocks = venue_blocks(svc, tokens, hours, clock.now(), use_24h=use_24h)
    empty = EmptyState(
        NO_VENUE,
        icon=ft.Icons.LOCATION_OFF_OUTLINED,
        body=NO_VENUE_BODY,
        identifier=f"{SCREEN}.empty",
    )
    return AppScaffold(
        title=TITLE,
        body=InfoBody(blocks, block="venues-hours", screen=SCREEN, empty=empty),
    )


def venue_blocks(
    svc: Services,
    tokens: Tokens,
    hours: tuple[ServiceHours, ...],
    now: datetime,
    *,
    use_24h: bool,
) -> list[ft.Control]:
    """Return the page's blocks at ``now``, in reading order; none without hours.

    Args:
        svc: The session's services: the year's facts, the launcher, the clipboard.
        tokens: The theme's tokens, for ``live``.
        hours: The year's ``[[venue_hours]]``; empty shows the feed's block instead.
        now: The current instant (``clock.now()``).
        use_24h: Whether the device shows 24-hour times (D-35).
    """
    if not hours:
        return []
    info = svc.year.conference
    zone = info.zone
    blocks: list[ft.Control] = []
    if info.address:
        blocks.append(address_card(svc, info))
    note = zone_note(now, zone, info.time_zone_name, now.astimezone().utcoffset())
    if note is not None:
        blocks.append(zone_line(note))
    statuses: Mapping[str, HoursStatus] = (
        hours_status(hours, now, zone, use_24h=use_24h) or {}
    )
    today = local_date(now, zone)
    blocks += [
        service_card(
            item, statuses.get(item.service), tokens, zone, today, use_24h=use_24h
        )
        for item in hours
    ]
    return blocks


def directions_url(directions: Directions, *, ios: bool) -> str:
    """Return the link that opens a maps app at the venue (D-313).

    Ionic's two forms (MAP-11): Apple Maps' web address on iOS, which the system hands
    to Maps, a pin named for the entrance with walking directions (``dirflg=w``); a
    ``geo:`` link on Android, which any maps app answers, with the pin named the same.

    Args:
        directions: The year's ``[directions]``.
        ios: Whether the device is an iPhone or an iPad.
    """
    point = f"{directions.latitude},{directions.longitude}"
    label = quote(directions.label)
    if ios:
        return f"https://maps.apple.com/?q={label}&ll={point}&dirflg=w"
    return f"geo:{point}?q={point}({label})"


def service_key(service: str) -> str:
    """Return a service's identifier key: "Lost & found" is ``lost_found``.

    Args:
        service: The service's name, as the year data writes it.
    """
    return re.sub(r"[^a-z0-9]+", "_", service.casefold()).strip("_")


def address_card(svc: Services, info: ConferenceInfo) -> ft.Control:
    """Return the card with the venue's name and address, Directions and Copy address.

    Directions shows only when the year has ``[directions]``. It leaves the app, so
    it is a link whose name ends with "Opens in another app" (D-182, D-186).

    Args:
        svc: The session's services, for the launcher and the clipboard.
        info: The year's facts: the venue, its address and its point.
    """

    @report_errors
    async def copy_address() -> None:
        await copy_text(svc, info.address, ADDRESS_COPIED, ADDRESS_NOT_COPIED)

    buttons: list[ft.Control] = []
    if (directions := info.directions) is not None:
        point = directions

        @report_errors
        async def open_directions() -> None:
            ios = ft.context.page.platform is ft.PagePlatform.IOS
            await open_link(svc, directions_url(point, ios=ios), app=True)

        button = ft.FilledTonalButton(
            ft.Text(
                DIRECTIONS, semantics_label=f"{DIRECTIONS}\n{OPENS_IN[LinkKind.APP]}"
            ),
            icon=ft.Icons.DIRECTIONS_OUTLINED,
            on_click=open_directions,
        )
        buttons.append(external(f"{SCREEN}.directions", button))
    buttons.append(
        named(
            f"{SCREEN}.copy_address",
            ft.OutlinedButton(
                COPY_ADDRESS, icon=ft.Icons.CONTENT_COPY_OUTLINED, on_click=copy_address
            ),
        )
    )
    return card(
        [
            heading(info.venue, f"{SCREEN}.address"),
            ft.Text(
                info.address, theme_style=ft.TextThemeStyle.BODY_LARGE, selectable=True
            ),
            # A wrapping row: at 200 % text the two buttons stack, nothing clips.
            ft.Row(buttons, wrap=True, spacing=8, run_spacing=8),
        ]
    )


def zone_line(note: str) -> ft.Control:
    """Return the line that says the hours are conference time (D-35, D-240).

    Args:
        note: ``zone_note()``'s words: "Times are Pacific Time (PDT)".
    """
    return ft.Container(
        ft.Row(
            [
                # Decorative: the words say it.
                ft.Icon(ft.Icons.PUBLIC, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Semantics(
                    identifier=f"{SCREEN}.zone_note",
                    expand=True,
                    content=ft.Text(
                        note,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.symmetric(horizontal=GUTTER, vertical=8),
    )


def service_card(
    item: ServiceHours,
    status: HoursStatus | None,
    tokens: Tokens,
    zone: tzinfo,
    today: date,
    *,
    use_24h: bool,
) -> ft.Control:
    """Return a service's card: name, status, where, its days and its note.

    Not one node (``semantic_container=False``, as Help's card, D-211): a screen
    reader stops on the name, a heading, then on each line.

    Args:
        item: The service and its hours.
        status: Its status now; None off-season or for a service without hours.
        tokens: The theme's tokens, for ``live``.
        zone: The conference's zone, which the hours are written in.
        today: The conference-local day, whose hours are in bold.
        use_24h: Whether the device shows 24-hour times (D-35).
    """
    key = f"{SCREEN}.service.{service_key(item.service)}"
    lines: list[ft.Control] = [heading(item.service, key)]
    if status is not None:
        lines.append(status_label(status, tokens, key))
    if item.location:
        lines.append(
            ft.Row(
                [
                    # Decorative: the words say where.
                    ft.Icon(ft.Icons.PLACE_OUTLINED, size=18),
                    ft.Text(item.location, expand=True),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
    lines += [
        day_line(opening.date, *opening.span(zone), zone, today, use_24h=use_24h)
        for opening in item.open
    ]
    if item.note:
        lines.append(
            ft.Text(
                item.note,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return card(lines)


def status_label(status: HoursStatus, tokens: Tokens, key: str) -> ft.Control:
    """Return a service's status: an icon and its words, never a chip (ux.md §6.7).

    Nothing happens on a tap, so it is no control: the icon is decorative and the
    words are read as words ("Open now, until 6:00 PM"). Open now is in ``live``, its
    icon too; the words say it, so colour is never the only signal (D-33).

    Args:
        status: What ``hours_status()`` says of the service now.
        tokens: The theme's tokens, for ``live``.
        key: The service's identifier; the label's is ``<key>.status``.
    """
    color = tokens.live if status.kind == "open" else ft.Colors.ON_SURFACE_VARIANT
    return ft.Row(
        [
            ft.Icon(STATUS_ICONS[status.kind], size=18, color=color),
            ft.Semantics(
                identifier=f"{key}.status",
                expand=True,
                content=ft.Text(
                    status.label,
                    semantics_label=status.spoken,
                    theme_style=ft.TextThemeStyle.LABEL_LARGE,
                    color=color,
                ),
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def day_line(
    day: date,
    opens: datetime,
    closes: datetime,
    zone: tzinfo,
    today: date,
    *,
    use_24h: bool,
) -> ft.Control:
    """Return one day's hours: "Thu, May 14 · 7:30 AM–6:00 PM", today's in bold.

    One node read in full words ("Thursday, May 14, 7:30 AM to 6:00 PM, today"): the
    bold says today on screen, the word says it to a screen reader. The line breaks
    only at its "·", never inside the day or the times (``on_screen()``).

    Args:
        day: The conference-local day.
        opens: When it opens, aware.
        closes: When it closes, aware.
        zone: The conference's zone.
        today: The conference-local day today.
        use_24h: Whether the device shows 24-hour times (D-35).
    """
    is_today = day == today
    shown = time_range_label(opens, closes, zone, use_24h=use_24h)
    spoken = (
        f"{day_heading(day)}, {time_label(opens, zone, use_24h=use_24h)} to "
        f"{time_label(closes, zone, use_24h=use_24h)}"
    )
    return ft.Semantics(
        label=f"{spoken}, today" if is_today else spoken,
        container=True,
        exclude_semantics=True,
        content=ft.Text(
            f"{on_screen(day_label(day))} · {on_screen(shown)}",
            weight=ft.FontWeight.BOLD if is_today else None,
        ),
    )


def heading(text: str, identifier: str) -> ft.Control:
    """Return a card's level-2 heading, a node of its own (D-211).

    Args:
        text: The venue's or the service's name.
        identifier: For UI flows: ``venue.address``, ``venue.service.<key>``.
    """
    return ft.Semantics(
        identifier=identifier,
        header=True,
        heading_level=2,
        container=True,
        content=ft.Text(text, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
    )


def card(lines: list[ft.Control]) -> ft.Control:
    """Return an outlined card of ``lines``, ``GUTTER`` from the page's sides.

    Outlined, so its fill is the surface, on which ``live`` reads at AA (D-24).

    Args:
        lines: Its content, top to bottom.
    """
    return ft.Container(
        ft.Card(
            ft.Container(ft.Column(lines, spacing=8), padding=16),
            variant=ft.CardVariant.OUTLINED,
            margin=0,
            semantic_container=False,  # else the card reads as one node (D-211)
        ),
        padding=ft.Padding.symmetric(horizontal=GUTTER, vertical=8),
    )
