"""Tests for the venue hours' year data and its rules (``year_info.py``; #412, D-282).

2026's ``[[venue_hours]]`` are transcribed from the bundled feed's ``venues-hours`` block,
so a test reads that block and compares; 2025 has no table. The loader refuses an
overlap, reversed times and a day outside the conference, naming file, entry and field.
"""

import html
import json
import re
import shutil
from datetime import date, time
from pathlib import Path

import pytest

from pycon_us import config
from pycon_us.config import YearDataError, load_year
from pycon_us.core.hours import Opening, ServiceHours
from pycon_us.year_info import check_venue_hours

CONFERENCE = load_year(2026).conference
FILE = "2026/content.toml"

# The feed's headings for the services it gives hours, and the names the app uses.
FEED_SERVICES = {
    "Registration Hours & Location:": "Registration",
    "Information Desk Hours & Location:": "Information desk",
    "Swag Pickup Hours & Location": "Swag pickup",
    "Attendee Quiet Room": "Quiet room",
}
_HOURS_LINE = re.compile(r"^\w+, May (\d+): (\S+) - (\S+)$")
_CLOCK = re.compile(r"^(\d{1,2})(?::(\d\d))?(am|pm)$")


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the bundled year data."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    """Replace the first ``old`` in ``path`` with ``new``; ``old`` must be there."""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def clock(text: str) -> time:
    """The feed's "7:30am", "6pm" or "12pm" as a time."""
    found = _CLOCK.match(text)
    assert found, text
    hour, minute, meridiem = int(found[1]), int(found[2] or 0), found[3]
    return time(hour % 12 + (12 if meridiem == "pm" else 0), minute)


def feed_hours() -> dict[str, tuple[str, tuple[Opening, ...]]]:
    """The snapshot's ``venues-hours`` block: each service's location and openings."""
    raw = load_year(2026).read_snapshot().raw.decode()
    block = html.unescape(json.loads(raw)["conference"]["content"]["venues-hours"])
    found: dict[str, tuple[str, tuple[Opening, ...]]] = {}
    for section in block.split("<h3>")[1:]:
        heading, body = section.split("</h3>", 1)
        if heading not in FEED_SERVICES:
            continue
        location = re.search(r"<p>(.*?)</p>", body)
        assert location, heading
        openings = []
        for item in re.findall(r"<li>(.*?)</li>", body):
            line = _HOURS_LINE.match(item)
            assert line, item
            openings.append(
                Opening(date(2026, 5, int(line[1])), clock(line[2]), clock(line[3]))
            )
        found[FEED_SERVICES[heading]] = (location[1], tuple(openings))
    return found


def test_2026_matches_the_feed_s_venue_hours_block() -> None:
    """Each service the feed gives hours has the same location and openings in 2026's data."""
    hours = {item.service: item for item in load_year(2026).content.venue_hours}
    feed = feed_hours()
    assert set(feed) == set(FEED_SERVICES.values())
    for service, (location, openings) in feed.items():
        assert (hours[service].location, hours[service].open) == (location, openings)


def test_2026_lists_six_services_with_lost_and_found_and_no_luggage_check() -> None:
    """2026 has the feed's six services; the two without hours carry a note instead."""
    hours = load_year(2026).content.venue_hours
    assert [item.service for item in hours] == [
        "Registration",
        "Information desk",
        "Swag pickup",
        "Quiet room",
        "Lost & found",
        "Luggage check",
    ]
    without = {item.service: item for item in hours if not item.open}
    assert without["Lost & found"].location == "Room 203AB"
    assert "information desk" in without["Lost & found"].note
    assert without["Luggage check"] == ServiceHours(
        "Luggage check", note="There is no luggage check this year."
    )


def test_2025_has_no_table_and_loads() -> None:
    """A year without ``[[venue_hours]]`` loads, with none: its page shows the feed's block."""
    assert load_year(2025).content.venue_hours == ()


def service(*openings: Opening, name: str = "Desk", **texts: str) -> ServiceHours:
    """A service with ``openings`` and optional texts, for the rule tests."""
    return ServiceHours(name, open=openings, **texts)


def opening(day: int, opens: int, closes: int) -> Opening:
    """An opening on a day of May 2026, from and to whole hours."""
    return Opening(date(2026, 5, day), time(opens), time(closes))


@pytest.mark.parametrize(
    ("hours", "message"),
    [
        (
            (service(opening(14, 9, 12), opening(14, 11, 15)),),
            (
                "venue_hours[0].open[1].opens: overlaps venue_hours[0].open[0] "
                "(2026-05-14, 09:00:00 to 12:00:00)"
            ),
        ),
        (
            (service(opening(14, 9, 17), opening(15, 9, 17), opening(14, 8, 10)),),
            (
                "venue_hours[0].open[2].opens: overlaps venue_hours[0].open[0] "
                "(2026-05-14, 09:00:00 to 17:00:00)"
            ),
        ),
        (
            (service(opening(14, 10, 12), opening(14, 9, 18)),),
            (
                "venue_hours[0].open[1].opens: overlaps venue_hours[0].open[0] "
                "(2026-05-14, 10:00:00 to 12:00:00)"
            ),
        ),
        (
            (service(opening(14, 18, 9)),),
            "venue_hours[0].open[0].closes: 09:00:00 is not after opens (18:00:00)",
        ),
        (
            (service(opening(14, 9, 9)),),
            "venue_hours[0].open[0].closes: 09:00:00 is not after opens (09:00:00)",
        ),
        (
            (service(opening(12, 9, 17)),),
            (
                "venue_hours[0].open[0].date: 2026-05-12 is not a day of the conference "
                "(2026-05-13 to 2026-05-19)"
            ),
        ),
        (
            (service(opening(20, 9, 17)),),
            (
                "venue_hours[0].open[0].date: 2026-05-20 is not a day of the conference "
                "(2026-05-13 to 2026-05-19)"
            ),
        ),
        (
            (service(opening(14, 9, 17)), service(opening(15, 9, 17), name="desk ")),
            "venue_hours[1].service: 'desk ' is listed twice",
        ),
        ((service(opening(14, 9, 17), name=" "),), "venue_hours[0].service: is empty"),
        (
            (service(opening(14, 9, 17), location="  "),),
            "venue_hours[0].location: is empty",
        ),
        ((service(opening(14, 9, 17), pin=" "),), "venue_hours[0].pin: is empty"),
        (
            (service(opening(14, 9, 17)), service(name="Lockers")),
            "venue_hours[1].note: a service without hours needs a note",
        ),
    ],
)
def test_the_rules_refuse_a_broken_entry_naming_entry_and_field(
    hours: tuple[ServiceHours, ...], message: str
) -> None:
    """Overlaps, reversed times, days outside the conference, twins and blanks are refused."""
    with pytest.raises(YearDataError) as error:
        check_venue_hours(hours, CONFERENCE, FILE)
    assert str(error.value) == f"{FILE}: {message}"


def test_the_rules_accept_touching_openings_and_the_conference_s_edges() -> None:
    """One opening may close as the next opens, and the first and last days are in."""
    check_venue_hours(
        (
            service(opening(14, 9, 12), opening(14, 12, 17)),
            service(opening(13, 7, 8), opening(19, 16, 17), name="Sprints desk"),
            service(name="Lockers", note="None this year."),
        ),
        CONFERENCE,
        FILE,
    )


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "{ date = 2026-05-14, opens = 07:30:00, closes = 18:00:00 }",
            "{ date = 2026-05-14, opens = 18:30:00, closes = 18:00:00 }",
            "venue_hours[0].open[1].closes: 18:00:00 is not after opens (18:30:00)",
        ),
        (
            "{ date = 2026-05-14, opens = 07:30:00, closes = 18:00:00 }",
            "{ date = 2026-05-13, opens = 17:30:00, closes = 19:00:00 }",
            (
                "venue_hours[0].open[1].opens: overlaps venue_hours[0].open[0] "
                "(2026-05-13, 07:30:00 to 18:00:00)"
            ),
        ),
        (
            "{ date = 2026-05-14, opens = 07:30:00, closes = 18:00:00 }",
            "{ date = 2026-06-14, opens = 07:30:00, closes = 18:00:00 }",
            (
                "venue_hours[0].open[1].date: 2026-06-14 is not a day of the conference "
                "(2026-05-13 to 2026-05-19)"
            ),
        ),
        (
            "{ date = 2026-05-14, opens = 07:30:00, closes = 18:00:00 }",
            '{ date = 2026-05-14, opens = "7:30am", closes = 18:00:00 }',
            "venue_hours[0].open[1].opens: expected a time, got '7:30am'",
        ),
        (
            'service = "Swag pickup"',
            'service = "Swag pickup"\nhours = "9 to 5"',
            "venue_hours[2].hours: unknown key",
        ),
    ],
)
def test_the_loader_names_the_file_entry_and_field(
    data_dir: Path, old: str, new: str, message: str
) -> None:
    """A broken ``[[venue_hours]]`` entry in a year's file fails its load with the path."""
    edit(data_dir / "2026" / "content.toml", old, new)
    with pytest.raises(YearDataError) as error:
        load_year(2026, data_dir)
    assert str(error.value) == f"{FILE}: {message}"
