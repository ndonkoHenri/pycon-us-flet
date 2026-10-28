"""Venue & hours' cards: a service's card, its status, its days, and the card itself.

``screens/venue.py`` builds the page (MAP-09, D-313); here are the parts its cards are
made of: ``service_card()`` with its ``status_label()`` and a ``day_line()`` per day,
the level-2 ``heading()`` and the outlined ``card()`` the address card shares.
"""

from datetime import date, datetime, tzinfo

import flet as ft

from pycon_us.core.hours import HoursStatus, ServiceHours
from pycon_us.core.timefmt import (
    day_heading,
    day_label,
    on_screen,
    time_label,
    time_range_label,
)
from pycon_us.theme import Tokens
from pycon_us.ui.info_page import GUTTER

STATUS_ICONS = {
    "open": ft.Icons.CHECK_CIRCLE_OUTLINE,
    "later_today": ft.Icons.SCHEDULE,
    "another_day": ft.Icons.EVENT_OUTLINED,
    "closed_today": ft.Icons.DO_NOT_DISTURB_ON_OUTLINED,
}
"""Each status's decorative icon beside its words, outlined (D-27)."""


def service_card(
    item: ServiceHours,
    key: str,
    status: HoursStatus | None,
    tokens: Tokens,
    zone: tzinfo,
    today: date,
    *,
    use_24h: bool,
    footer: ft.Control | None = None,
    location: ft.Control | None = None,
) -> ft.Control:
    """Return a service's card: name, status, where, its days, its note and its pin.

    Not one node (``semantic_container=False``, as Help's card, D-211): a screen
    reader stops on the name, a heading, then on each line.

    Args:
        item: The service and its hours.
        key: Its identifier, ``venue.service.<key>``; its lines' start with it.
        status: Its status now; None off-season or for a service without hours.
        tokens: The theme's tokens, for ``live``.
        zone: The conference's zone, which the hours are written in.
        today: The conference-local day, whose hours are in bold.
        use_24h: Whether the device shows 24-hour times (D-35).
        footer: A row under the lines, edge to edge: the Quiet room's sponsor credit.
        location: Its ``LocationCard`` (``spot_card()``), last of the lines; None
            for a service without a pin.
    """
    lines: list[ft.Control] = [heading(item.service, key)]
    if status is not None:
        lines.append(status_label(status, tokens, key))
    if item.location:
        lines.append(
            ft.Row(
                [
                    # Decorative: the words say where. One line tall (D-373).
                    ft.Icon(ft.Icons.PLACE_OUTLINED, size=20, apply_text_scaling=True),
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
    if location is not None:
        lines.append(location)
    return card(lines, footer)


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
            # One LABEL_LARGE line tall at every text size (D-373).
            ft.Icon(
                STATUS_ICONS[status.kind], size=20, apply_text_scaling=True, color=color
            ),
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
    at its "·" or after the range's dash (D-229), never inside the day or a time
    (``on_screen()``).

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


def card(lines: list[ft.Control], footer: ft.Control | None = None) -> ft.Control:
    """Return an outlined card of ``lines``, ``GUTTER`` from the page's sides.

    Outlined, so its fill is the surface, on which ``live`` reads at AA (D-24).

    Args:
        lines: Its content, top to bottom.
        footer: A row under them, outside their padding, so its own 16 dp inset lines
            it up with them.
    """
    body: ft.Control = ft.Container(ft.Column(lines, spacing=8), padding=16)
    if footer is not None:
        body = ft.Column([body, footer], spacing=0)
    return ft.Container(
        ft.Card(
            body,
            variant=ft.CardVariant.OUTLINED,
            margin=0,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # a footer's ink stays inside
            semantic_container=False,  # else the card reads as one node (D-211)
        ),
        padding=ft.Padding.symmetric(horizontal=GUTTER, vertical=8),
    )
