"""Venue hours and the open-now rule (MAP-09, DATA-23; D-282).

The year's ``content.toml`` says when each venue service (registration, the information
desk, the quiet room…) is open, as ``[[venue_hours]]`` entries the loader builds into the
dataclasses below (``year_info`` checks their rules). ``hours_status()`` answers "is it
open now?" for every service at once: "Open now · until 6:00 PM", "Opens 7:30 AM", "Opens
tomorrow at 7:30 AM", "Closed today", or nothing at all outside the days the venue's
services open (``days()``), when no label would help.

Every function is pure: ``now`` and the conference's zone are arguments (D-43). Opening
hours are local wall times on conference-local days, so a device in another zone still
sees the venue's own hours, and an opening is half-open like a session (D-179): the
opening minute is open, the closing minute closed.
"""

import datetime as dt  # a module name, since the fields are called `date`, as in the TOML
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from pycon_us.core.timefmt import day_heading, day_label, local_date, time_label


@dataclass(frozen=True)
class Opening:
    """One stretch of a day when a service is open, in conference time.

    Attributes:
        date: The conference-local day.
        opens: When it opens, a local wall time.
        closes: When it closes, later the same day; from that minute it is closed.
    """

    date: dt.date
    opens: dt.time
    closes: dt.time

    def span(self, zone: dt.tzinfo) -> tuple[dt.datetime, dt.datetime]:
        """Return when it opens and closes as aware instants in ``zone``."""
        return (
            dt.datetime.combine(self.date, self.opens, tzinfo=zone),
            dt.datetime.combine(self.date, self.closes, tzinfo=zone),
        )


@dataclass(frozen=True)
class ServiceHours:
    """A venue service and when it is open, one ``[[venue_hours]]`` entry.

    Attributes:
        service: The service's name, unique in the year ("Registration").
        location: Where it is, as the venue signs it ("Promenade Lobby (Main
            Entrance)"); empty when it has no place (a service the venue does not
            offer this year).
        pin: The floor-plan pin that shows it, a ``map.toml`` key (checked there once
            the year has one); empty without one.
        note: One more line about it ("Extra T-shirts on Sunday, May 17, 11 AM to
            1 PM."); empty without one. A service with no hours of its own has one.
        open: When it is open; empty for a service without hours of its own, which
            gets no status.
    """

    service: str
    location: str = ""
    pin: str = ""
    note: str = ""
    open: tuple[Opening, ...] = ()


type HoursKind = Literal["open", "later_today", "another_day", "closed_today"]
"""Where a service stands: open now, opening later today, on another day, or done."""


@dataclass(frozen=True)
class HoursStatus:
    """What a service's status label says at an instant (MAP-09).

    Attributes:
        kind: Where the service stands; ``"open"`` is drawn in ``live``.
        label: What the screen shows: "Open now · until 6:00 PM", "Opens 7:30 AM",
            "Opens tomorrow at 7:30 AM", "Opens Thu, May 14 at 9:00 AM", "Closed today".
        spoken: The same for screen readers, with a comma for the "·" ("Open now,
            until 6:00 PM") and the day's name in full ("Opens Thursday, May 14 at
            9:00 AM"); equal to ``label`` otherwise.
    """

    kind: HoursKind
    label: str
    spoken: str


CLOSED_TODAY = HoursStatus("closed_today", "Closed today", "Closed today")
"""A service that does not open again today, nor on a later day of the season."""


def days(hours: Iterable[ServiceHours]) -> tuple[dt.date, ...]:
    """Return the days any service opens on, in order: the season the labels show in.

    Args:
        hours: The year's ``venue_hours``.
    """
    return tuple(sorted({opening.date for item in hours for opening in item.open}))


def hours_status(
    hours: Iterable[ServiceHours], now: dt.datetime, zone: dt.tzinfo, *, use_24h: bool
) -> Mapping[str, HoursStatus] | None:
    """Return each service's status at ``now``, or None off-season.

    Off-season is any conference-local day before the first or after the last of
    ``days()``: before the venue opens and once it has closed for the year a label
    would only say "Closed", so the page shows the hours alone. In season, every
    service with hours of its own has a status (one without hours has none):

    - open now (``opens <= now < closes``): "Open now · until 6:00 PM";
    - else its next opening, later today: "Opens 7:30 AM"; on the next day:
      "Opens tomorrow at 7:30 AM"; on a later one: "Opens Thu, May 14 at 9:00 AM";
    - else, with no opening left in the season: "Closed today".

    Args:
        hours: The year's ``venue_hours``.
        now: The current instant, aware (``clock.now()``).
        zone: The conference's zone, in which the hours are written (D-43).
        use_24h: Whether the device shows 24-hour times (D-35).

    Returns:
        The statuses by service name, in the year data's order; None off-season.

    Raises:
        ValueError: ``now`` is naive.
    """
    hours = tuple(hours)
    season = days(hours)
    today = local_date(now, zone)  # refuses a naive now
    if not season or not season[0] <= today <= season[-1]:
        return None
    return {
        item.service: _status(item.open, now, zone, use_24h=use_24h)
        for item in hours
        if item.open
    }


def _status(
    openings: tuple[Opening, ...], now: dt.datetime, zone: dt.tzinfo, *, use_24h: bool
) -> HoursStatus:
    spans = sorted(opening.span(zone) for opening in openings)
    for opens, closes in spans:
        if opens <= now < closes:
            until = time_label(closes, zone, use_24h=use_24h)
            return HoursStatus(
                "open", f"Open now · until {until}", f"Open now, until {until}"
            )
    upcoming = [opens for opens, _ in spans if opens > now]
    if not upcoming:
        return CLOSED_TODAY
    opens = upcoming[0]
    at = time_label(opens, zone, use_24h=use_24h)
    day = local_date(opens, zone)
    today = local_date(now, zone)
    if day == today:
        label = f"Opens {at}"
        return HoursStatus("later_today", label, label)
    if day == today + dt.timedelta(days=1):
        label = f"Opens tomorrow at {at}"
        return HoursStatus("another_day", label, label)
    return HoursStatus(
        "another_day",
        f"Opens {day_label(day)} at {at}",
        f"Opens {day_heading(day)} at {at}",
    )
