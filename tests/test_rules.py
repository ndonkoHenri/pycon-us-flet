"""Named tests for Ionic's processing rules (D-41; DATA-04..07, DATA-27, SCHED-19).

Each test asserts a concrete case of the recorded 2025 or 2026 feed, or of a copy of it with
one record changed, under two machine time zones (``machine_tz``).
"""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.feed import process
from pycon_us.core.rules import plain_text, track
from tests.feeds import changed, document, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")

PACIFIC = ZoneInfo("America/Los_Angeles")
EASTERN = ZoneInfo("America/New_York")


def pacific(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, tzinfo=PACIFIC)


def test_names_become_plain_text() -> None:
    assert (
        plain_text("[Posters (Hall AB)](/2026/schedule/posters/list/)")
        == "Posters (Hall AB)"
    )
    assert plain_text("[Yes, You Can] Test SQL") == "[Yes, You Can] Test SQL"
    assert plain_text("Dask &amp; Xarray ") == "Dask & Xarray"
    assert (
        plain_text("CANCELLED: <s>Introduction to Sprints Workshop</s>")
        == "CANCELLED: Introduction to Sprints Workshop"
    )


def test_track_is_the_kind_capitalised_except_sponsor_workshops() -> None:
    """DATA-14: track keys as config's track registry names them."""
    assert [
        track(k) for k in ("talk", "ai", "lightning-talks", "sponsor-workshop")
    ] == [
        "Talk",
        "Ai",
        "Lightning-talks",
        "Sponsor Presentation",
    ]


def test_placeholder_slots_dropped_but_posters_and_breaks_kept() -> None:
    """DATA-04: cancelled stubs go; poster and break slots of the same shape collapse."""
    dropped = processed(2026).dropped
    assert dropped["placeholder"] == ("130", "34", "1136", "32")
    assert processed(2025).dropped["placeholder"] == ("34",)
    poster_slots = [s for s in document(2026)["schedule"] if s["kind"] == "poster"]
    assert poster_slots[0]["name"] == "poster" and not poster_slots[0]["description"]
    assert {str(s["conf_key"]) for s in poster_slots} <= set(dropped["collapsed"])


def test_open_space_slots_are_dropped_from_the_schedule() -> None:
    """DATA-04: free rooms, and the booked ones the open-spaces list also has."""
    dropped = processed(2026).dropped
    assert (
        len(dropped["available-open-space"]),
        len(dropped["open-space-duplicate"]),
    ) == (
        484,
        7,
    )
    assert (
        "1140" in dropped["open-space-duplicate"]
    )  # "5K Fun Run", also open space 119


def test_posters_plenary_is_dropped_as_a_copy_of_the_posters_row() -> None:
    """DATA-04: "[Posters (Hall AB)](...)" is a plenary copy of the collapsed row."""
    assert processed(2026).dropped["posters-plenary"] == ("179",)


def test_blank_slots_are_dropped() -> None:
    def blank(doc: dict[str, Any]) -> None:
        doc["schedule"][4]["kind"] = "blank"  # 196, "Registration Desk Opens"
        doc["schedule"][5]["name"] = "Slot"  # 198

    data = process(changed(2026, blank), settings(2026))
    assert data.dropped["blank"] == ("196", "198")


def test_open_spaces_become_sessions_with_offset_ids() -> None:
    """DATA-05: id conf_key + 9000, track Open Space, the room_display as location."""
    data = processed(2026)
    run = data.sessions["9119"]  # open space 119, "5K Fun Run", room "Elsewhere"
    assert (run.name, run.kind, run.track, run.location) == (
        "5K Fun Run",
        "open-space",
        "Open Space",
        "Out Front of Hyatt Regency",
    )
    assert (run.start, run.end, run.day) == (
        pacific(16, 7),
        pacific(16, 8),
        pacific(16, 7).date(),
    )
    assert run.description.startswith("Meet out front of Hyatt Regency 7AM")
    assert run.url == "https://us.pycon.org/2026/schedule/open-spaces/#OpenSpace-119"
    assert run.image_url.endswith("/2026/media/open_spaces_images/running-sand.png")
    assert run.speaker_ids == () and run.in_timeline
    assert sum(s.kind == "open-space" for s in data.sessions.values()) == 123
    assert sum(s.kind == "open-space" for s in processed(2025).sessions.values()) == 146


def test_open_space_image_is_made_absolute() -> None:
    def relative(doc: dict[str, Any]) -> None:
        doc["open-spaces"][0]["image_url"] = "/2026/media/open_spaces_images/x.png"

    data = process(changed(2026, relative), settings(2026))
    space = document(2026)["open-spaces"][0]
    session = data.sessions[str(space["conf_key"] + 9000)]
    assert (
        session.image_url == "https://us.pycon.org/2026/media/open_spaces_images/x.png"
    )


def test_unscheduled_open_space_is_dropped() -> None:
    """DATA-05: without a start, an end or a room it is a proposal, not a session."""

    def unschedule(doc: dict[str, Any]) -> None:
        doc["open-spaces"][0]["start"] = None
        del doc["open-spaces"][1]["end"]
        doc["open-spaces"][2].update(room_display=" ", room="")

    data = process(changed(2026, unschedule), settings(2026))
    ids = tuple(str(s["conf_key"] + 9000) for s in document(2026)["open-spaces"][:3])
    assert data.dropped["unscheduled-open-space"] == ids
    assert not set(ids) & set(data.sessions)
    assert data.skipped == ()


def test_open_space_without_room_display_uses_its_room() -> None:
    """DATA-05: Ionic checked room_display or room but showed only room_display."""

    def no_display(doc: dict[str, Any]) -> None:
        doc["open-spaces"][0]["room_display"] = ""

    data = process(changed(2026, no_display), settings(2026))
    assert data.sessions["9119"].location == "Elsewhere"


def test_lunch_row_spans_earliest_start_to_latest_end() -> None:
    """DATA-06, SCHED-19: Friday's staggered "Lunch (Hall AB)" slots make one row."""
    lunch = processed(2026).sessions["break-Expo Hall AB-2026-05-15T12:30:00-07:00"]
    assert (lunch.name, lunch.track, lunch.location) == (
        "Lunch",
        "Break",
        "Expo Hall AB",
    )
    assert (lunch.start, lunch.end) == (pacific(15, 12, 30), pacific(15, 14))


def test_one_lunch_row_per_day_that_has_lunch() -> None:
    """DATA-06: Thursday to Sunday in 2026; every day in 2025."""
    for year, expected in ((2026, 4), (2025, 5)):
        lunches = [
            s.day for s in processed(year).sessions.values() if s.name == "Lunch"
        ]
        assert len(lunches) == len(set(lunches)) == expected


def test_all_posters_of_a_day_fold_into_one_row() -> None:
    """DATA-06: 26 five-minute poster slots become one Posters row."""
    data = processed(2026)
    (row,) = [s for s in data.sessions.values() if s.kind == "poster" and s.in_timeline]
    assert row.id == "poster-Expo Hall AB-2026-05-17T09:30:00-07:00"
    assert (row.name, row.track, row.location) == ("Posters", "Poster", "Expo Hall AB")
    assert (row.start, row.end) == (pacific(17, 9, 30), pacific(17, 13))
    assert (row.description, row.speaker_ids) == ("", ())


def test_breaks_other_than_lunch_fold_per_start() -> None:
    """DATA-06: Friday's 10:30 and 16:00 breaks stay two rows."""
    friday = [
        (s.start, s.end)
        for s in processed(2026).sessions.values()
        if s.name == "Break" and s.day == pacific(15, 0).date()
    ]
    assert friday == [
        (pacific(15, 10, 30), pacific(15, 11)),
        (pacific(15, 16), pacific(15, 16, 30)),
    ]


def test_collapsed_ids_keep_ionics_form_with_the_room() -> None:
    """DATA-06, D-42: "<kind>-<room>-<start>", with an empty room for Wednesday's break."""
    data = processed(2026)
    wednesday = data.sessions["break--2026-05-13T12:30:00-07:00"]
    assert (wednesday.name, wednesday.location) == ("Break", "")
    coffee = data.sessions["break-Expo Hall AB-2026-05-15T08:00:00-07:00"]
    assert coffee.name == "Coffee"  # "(Hall AB)" moved to the room


def test_hall_rooms_get_the_years_prefix() -> None:
    """D-122: "Lunch (Hall C)" is in Expo Hall C in 2026; 2025's halls keep their names."""
    thursday = processed(2026).sessions["break-Expo Hall C-2026-05-14T12:30:00-07:00"]
    assert thursday.name == "Lunch"
    posters = processed(2025).sessions["poster-Hall A-2025-05-18T10:00:00-04:00"]
    assert posters.start == datetime(2025, 5, 18, 10, tzinfo=EASTERN)


def test_friday_to_sunday_break_at_lunchtime_is_renamed_lunch() -> None:
    """DATA-06: a "Break" from 12:00 to 13:59 on a main conference day is Lunch."""

    def noon(doc: dict[str, Any]) -> None:
        for slot in doc["schedule"]:
            if slot["conf_key"] == 154:  # Friday's 10:30 break
                slot.update(
                    start="2026-05-15T12:15:00-07:00", end="2026-05-15T12:45:00-07:00"
                )
            if slot["conf_key"] == 144:  # Wednesday's 12:30 break stays a Break
                slot["start"] = "2026-05-13T12:15:00-07:00"

    sessions = process(changed(2026, noon), settings(2026)).sessions.values()
    renamed = [s for s in sessions if s.start == pacific(15, 12, 15)]
    assert [s.name for s in renamed] == ["Lunch"]
    assert [s.name for s in sessions if s.start == pacific(13, 12, 15)] == ["Break"]


def test_empty_room_takes_a_later_slots_room() -> None:
    """DATA-06: as in Ionic, a row without a room adopts a later slot's "(Room)".

    Only a poster row can have one: its name becomes "Posters" before the room is read.
    """

    def roomless(doc: dict[str, Any]) -> None:
        for slot in doc["schedule"]:
            if slot["kind"] == "poster":
                slot.update(name="poster (Hall AB)", room="")

    data = process(changed(2026, roomless), settings(2026))
    row = data.sessions["poster-Expo Hall AB-2026-05-17T09:30:00-07:00"]
    assert (row.name, row.location) == ("Posters", "Expo Hall AB")


def test_poster_details_inherit_the_posters_row() -> None:
    """DATA-07: poster-detail-<conf_key>, at the Posters row's time and place."""
    data = processed(2026)
    row = data.sessions["poster-Expo Hall AB-2026-05-17T09:30:00-07:00"]
    details = [s for s in data.sessions.values() if s.id.startswith("poster-detail-")]
    assert [s.id for s in details] == [f"poster-detail-{p.id}" for p in data.posters]
    for detail, poster in zip(details, data.posters, strict=True):
        assert (detail.name, detail.description) == (poster.title, poster.description)
        assert (detail.kind, detail.track, detail.location) == (
            "poster",
            "Poster",
            row.location,
        )
        assert (detail.start, detail.end, detail.day) == (row.start, row.end, row.day)
        assert detail.speaker_ids == poster.speaker_ids
        assert not detail.in_timeline


def test_2025_nested_posters_become_posters_and_poster_details() -> None:
    """D-121, DATA-27: the 19 sessions of 2025's "Posters Session" slot are posters."""
    data = processed(2025)
    assert len(data.posters) == 19
    first = data.posters[0]
    assert first.id == "1544"
    assert first.title.startswith("Putting a Face to the Pattern")
    assert first.description.startswith("<p>In recent times")
    detail = data.sessions["poster-detail-1544"]
    assert (detail.location, detail.start) == (
        "Hall A",
        datetime(2025, 5, 18, 10, tzinfo=EASTERN),
    )
    assert set(first.speaker_ids) <= set(data.speakers)


def test_nested_sessions_of_another_kind_are_ignored_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DATA-27: Ionic's shared-session branch is not ported."""

    def nest(doc: dict[str, Any]) -> None:
        doc["schedule"][4]["sessions"] = [{"conf_key": 1, "name": "Inner"}]

    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = process(changed(2026, nest), settings(2026))
    assert caplog.messages == ["Ignored the nested sessions of slot 196 (DATA-27)"]
    assert len(data.posters) == 25 and data.skipped == ()


def test_posters_without_a_posters_row_get_no_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-123: no Posters row, no time to give the poster details."""

    def no_poster_slots(doc: dict[str, Any]) -> None:
        doc["schedule"] = [s for s in doc["schedule"] if s["kind"] != "poster"]

    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = process(changed(2026, no_poster_slots), settings(2026))
    assert not any(s.kind == "poster" for s in data.sessions.values())
    assert len(data.posters) == 25
    assert caplog.messages == ["No Posters row: the 25 posters get no session"]


def test_a_session_id_already_taken_is_skipped() -> None:
    """D-42: ids stay unique; the later session is skipped and recorded."""

    def collide(doc: dict[str, Any]) -> None:
        doc["schedule"][5]["conf_key"] = 9119  # open space 119's session id

    data = process(changed(2026, collide), settings(2026))
    assert data.skipped == ("session '5K Fun Run': duplicate id '9119'",)
    assert data.sessions["9119"].kind == "informational"


def test_dropped_slots_are_counted_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="pycon_us.core.feed"):
        processed(2026)
    (message,) = caplog.messages
    assert message == (
        "Dropped 484 available-open-space, 7 open-space-duplicate, 49 collapsed,"
        " 4 placeholder, 1 posters-plenary"
    )
