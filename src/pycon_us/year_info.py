"""The info pages' year data and its checks (D-263).

The info pages (Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF,
Social) say what the year's ``content.toml`` holds for them (D-45, INFO-05): each page's
table is a dataclass here, built through ``year_schema.build()`` as a field of
``config.Content``, and ``check_info()``, which ``config`` runs on every load, checks its
rules. A module of its own, as the Open spaces and Lightning talks pages' is
(``year_pages``, D-205), so ``config.py`` stays under D-66's ~400 lines while the six
pages' tables arrive.

So far Wi-Fi has its table, ``[wifi]`` (``WifiInfo``, D-280), Help & safety its two, and
Venue & hours its ``[[venue_hours]]`` (D-282), whose dataclasses are ``core.hours``'
since the open-now rule reads them, as feed processing reads ``core.rules``'
display-time overrides. The other pages' issues add theirs, with their rules, to this
module. Until a page has its table, or for a year that has none, the page shows the
feed's own block for it (``ui.info_page``).

Help & safety (D-281): ``[[safety_contacts]]`` (``SafetyContact``), the ways to report
a concern, each with the public page that shows it and the day someone checked it
there, and ``[help]`` (``HelpInfo``), the page's other lines and links.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from pycon_us.core.hours import ServiceHours
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

if TYPE_CHECKING:  # config imports this module; the types alone go the other way
    from pycon_us.config import ConferenceInfo, Content

CONTACT_KINDS = ("tel", "mailto", "https")
"""What a safety contact can be: a phone number, an email address or a web page."""

E164 = re.compile(r"\+[1-9]\d{6,14}")
"""A phone number in E.164: ``+``, a country code and the number, digits only."""

EMAIL = re.compile(r"[^@\s:/?#]+@[^@\s:/?#]+\.[^@\s:/?#.]+")
"""An email address: a local part, ``@``, and a host name with a dot."""


@dataclass(frozen=True)
class SafetyContact:
    """A way to report a concern, on Help & safety's Report a concern card (INFO-07).

    Safety-critical, so each one names the public page that shows it and the day
    someone last checked it there (D-45): a number found only in Ionic's code stays out.

    Attributes:
        label: What a tap does, as the row's title: "Email the Code of Conduct team".
        kind: ``tel``, ``mailto`` or ``https``; it names the row's identifier
            (``help.report.<kind>``), so a year lists each kind once.
        value: The number in E.164 (``+15625550100``), the address, or the ``https``
            URL.
        source: The public ``https`` page that shows the value.
        checked: The day the value was last checked on ``source``.
    """

    label: str
    kind: str
    value: str
    source: str
    checked: date

    @property
    def target(self) -> str:
        """The link a tap opens: ``tel:+1…``, ``mailto:…`` or the web page."""
        return self.value if self.kind == "https" else f"{self.kind}:{self.value}"


@dataclass(frozen=True)
class HelpInfo:
    """Help & safety's lines and links beside the contacts (INFO-07, INFO-11).

    Attributes:
        in_person: The card's last line: in danger, local emergency services first,
            with staff to help find the number; then reporting to any staff member.
        info_desk: Where the information desk is, in one line.
        lost_and_found: Where lost items go, in one line.
        quiet_room: Where the quiet room is, in one line.
        coc_summary: The Code of Conduct in a few sentences, in our words.
        coc_url: The full Code of Conduct, "Read the Code of Conduct".
        procedures_url: How reports are handled, "How reports are handled".
    """

    in_person: str
    info_desk: str
    lost_and_found: str
    quiet_room: str
    coc_summary: str
    coc_url: str
    procedures_url: str


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
    check_safety_contacts(content.safety_contacts, file)
    if content.help is not None:
        # The page's first stop is the card, and in_person is on it: a [help] without
        # a contact would leave the page with no way to report (D-281).
        if not content.safety_contacts:
            raise YearDataError(
                f"{file}: help: needs at least one [[safety_contacts]] entry"
                " (the Report a concern card)"
            )
        check_help(content.help, file)
    check_venue_hours(content.venue_hours, conference, file)


def check_safety_contacts(contacts: tuple[SafetyContact, ...], file: str) -> None:
    """Check the safety contacts: a label, a well-formed value, an https source.

    ``build()`` already refuses a contact without ``source`` or ``checked``.

    Args:
        contacts: The ``[[safety_contacts]]`` entries.
        file: The data file they come from, for the messages.

    Raises:
        YearDataError: A rule is broken, or two contacts share a kind.
    """
    seen: set[str] = set()
    for index, contact in enumerate(contacts):
        key = f"safety_contacts[{index}]"
        check_text(contact.label, file, f"{key}.label")
        if contact.kind not in CONTACT_KINDS:
            raise YearDataError(
                f"{file}: {key}.kind: {contact.kind!r} is not one of {CONTACT_KINDS}"
            )
        if contact.kind in seen:  # one row, one identifier per kind
            raise YearDataError(f"{file}: {key}.kind: duplicate kind {contact.kind!r}")
        seen.add(contact.kind)
        check_contact_value(contact, file, f"{key}.value")
        check_https(contact.source, file, f"{key}.source")


def check_contact_value(contact: SafetyContact, file: str, key: str) -> None:
    """Refuse a value its kind cannot open: a number not in E.164, a bad address.

    Args:
        contact: The contact whose value to check, by its kind.
        file: The data file it comes from, for the message.
        key: Its key in that file, for the message.

    Raises:
        YearDataError: The value is malformed for its kind.
    """
    if contact.kind == "https":
        check_https(contact.value, file, key)
    elif contact.kind == "tel" and not E164.fullmatch(contact.value):
        raise YearDataError(f"{file}: {key}: expected an E.164 number (+15625550100)")
    elif contact.kind == "mailto" and not EMAIL.fullmatch(contact.value):
        raise YearDataError(f"{file}: {key}: expected an email address")


def check_help(info: HelpInfo, file: str) -> None:
    """Check ``[help]``: no blank line, ``https://`` links.

    Args:
        info: The ``[help]`` table.
        file: The data file it comes from, for the messages.

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    for name in ("in_person", "info_desk", "lost_and_found", "quiet_room"):
        check_text(getattr(info, name), file, f"help.{name}")
    check_text(info.coc_summary, file, "help.coc_summary")
    check_https(info.coc_url, file, "help.coc_url")
    check_https(info.procedures_url, file, "help.procedures_url")


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
