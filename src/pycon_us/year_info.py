"""The info pages' year data and its checks (D-263).

The info pages (Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF,
Social) say what the year's ``content.toml`` holds for them (D-45, INFO-05): each page's
table is a dataclass here, built through ``year_schema.build()`` as a field of
``config.Content``, and ``check_info()``, which ``config`` runs on every load, checks its
rules. A module of its own, as the Open spaces and Lightning talks pages' is
(``year_pages``, D-205), so ``config.py`` stays under D-66's ~400 lines while the six
pages' tables arrive.

So far Wi-Fi has its table, ``[wifi]`` (``WifiInfo``, D-280), and Venue & hours its
``[[venue_hours]]`` (D-282), whose dataclasses are ``core.hours``' since the open-now rule
reads them, as feed processing reads ``core.rules``' display-time overrides. The other
pages' issues add theirs, with their rules, to this module. Until a page has its table,
or for a year that has none, the page shows the feed's own block for it
(``ui.info_page``).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pycon_us.core.hours import ServiceHours
from pycon_us.year_pages import check_text
from pycon_us.year_schema import YearDataError

if TYPE_CHECKING:  # config imports this module; the types alone go the other way
    from pycon_us.config import ConferenceInfo, Content


@dataclass(frozen=True)
class WifiInfo:
    """The conference network the Wi-Fi page shows and copies (INFO-08, D-280).

    Attributes:
        network: The network's name (its SSID), exactly as a phone lists it.
        password: Its password, exactly as it is typed.
    """

    network: str
    password: str


def check_info(content: Content, conference: ConferenceInfo, file: str) -> None:
    """Check the info pages' tables in a year's content.

    ``config``'s loader calls it with the content it built, after the other pages'
    checks, so a table that breaks a rule fails the load with a ``YearDataError`` that
    names the file and the key, as every year-data error does.

    Args:
        content: The year's ``content.toml``, built.
        conference: The year's facts, whose days the venue hours must fall on.
        file: The data file it comes from, for the messages (``2026/content.toml``).

    Raises:
        YearDataError: A table breaks one of its rules.
    """
    if (wifi := content.wifi) is not None:
        # A blank value would show nothing to read, and copy nothing to paste.
        check_text(wifi.network, file, "wifi.network")
        check_text(wifi.password, file, "wifi.password")
    check_venue_hours(content.venue_hours, conference, file)


def check_venue_hours(
    hours: tuple[ServiceHours, ...], conference: ConferenceInfo, file: str
) -> None:
    """Check the venue hours' rules (D-282).

    Each service has a name no other entry has (compared without case), no blank text,
    and, without hours of its own, a note that says why. Each opening is on a day of the
    conference (``first_day`` to ``last_day``), opens and closes on a whole minute
    (``07:30:00``, since the labels and the open-now rule work to the minute), opens
    before it closes, and does not overlap the service's other openings that day (one
    may close when the next opens).

    Args:
        hours: The ``[[venue_hours]]`` entries; empty for a year without them.
        conference: The year's facts, for its days.
        file: The data file they come from, for the messages.

    Raises:
        YearDataError: An entry breaks a rule; the message names the file, the entry
            and the field (``2026/content.toml: venue_hours[0].open[1].closes: …``).
    """
    first, last = conference.first_day, conference.last_day
    names: set[str] = set()
    for index, item in enumerate(hours):
        key = f"venue_hours[{index}]"
        check_text(item.service, file, f"{key}.service")
        for field in ("location", "pin", "note"):
            if text := getattr(item, field):  # optional: empty means not given
                check_text(text, file, f"{key}.{field}")
        name = item.service.strip().casefold()
        if name in names:
            raise YearDataError(
                f"{file}: {key}.service: {item.service!r} is listed twice"
            )
        names.add(name)
        if not item.open and not item.note:
            raise YearDataError(
                f"{file}: {key}.note: a service without hours needs a note"
            )
        for at, opening in enumerate(item.open):
            where = f"{key}.open[{at}]"
            if not first <= opening.date <= last:
                raise YearDataError(
                    f"{file}: {where}.date: {opening.date} is not a day of the "
                    f"conference ({first} to {last})"
                )
            for field in ("opens", "closes"):
                moment = getattr(opening, field)
                if moment.second or moment.microsecond:
                    raise YearDataError(
                        f"{file}: {where}.{field}: {moment} has seconds; "
                        "hours are whole minutes"
                    )
            if opening.closes <= opening.opens:
                raise YearDataError(
                    f"{file}: {where}.closes: {opening.closes} is not after "
                    f"opens ({opening.opens})"
                )
            for before, other in enumerate(item.open[:at]):
                if (
                    other.date == opening.date
                    and opening.opens < other.closes
                    and other.opens < opening.closes
                ):
                    raise YearDataError(
                        f"{file}: {where}.opens: overlaps {key}.open[{before}] "
                        f"({other.date}, {other.opens} to {other.closes})"
                    )
