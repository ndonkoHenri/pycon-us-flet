"""Tests for `map.toml`: the floor plans, the room and venue pins, and their loader.

DATA-32, MAP-07 (#372): the plans are S7's 2048-px WebP (D-312), every feed room has a
pin or is one of the year's other locations, and `normalize_room_key()` keys the pins
as Ionic did (D-122).
"""

import shutil
from pathlib import Path

import pytest
from PIL import Image

from pycon_us import config
from pycon_us.config import YearData, YearDataError, load_year
from pycon_us.core.expo import job_fair_tables
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData
from pycon_us.core.slugs import normalize_room_key, slugify_room
from pycon_us.year_map import ASSETS_DIR, Plan
from tests.feeds import YEARS, changed, document, move, processed

PLAN_BUDGET = 256 * 1024
"""S7's plans are 110-200 KB each as WebP 80 (D-312); this leaves a little room."""

THUMB_BUDGET = 64 * 1024
"""An 800-px WebP thumbnail is 30-60 KB."""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the bundled year data."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def edit(path: Path, old: str, new: str) -> None:
    """Replace the first `old` in `path` with `new`; `old` must be there."""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def rooms_without_pins(data: ConferenceData, year: YearData) -> list[str]:
    """The feed's rooms that have no pin and are not among the year's other locations."""
    other = {slugify_room(name) for name in year.content.other_locations}
    return [
        room.name
        for room in data.rooms.values()
        if room.slug not in other and year.map.room_pin(room.name) is None
    ]


def feed_room_strings(year: int) -> set[str]:
    """Every room name of `year`'s recorded feed: as written, and as processed."""
    names: set[str] = set()
    for item in document(year)["schedule"]:
        names.update(part.strip() for part in item["room"].split(",") if part.strip())
    for session in processed(year).sessions.values():
        names.update(session.rooms)
    return names


def test_2026_has_the_floor_plans_in_the_maps_order() -> None:
    """2026's plans are Ionic's five, in its order, then the expo's and the job fair's.

    MAP-02, MAP-03, with the 3D tour; the expo plan is the one the booths are on
    (EXPO-02), and the job fair's carries the note its pane shows (MAP-04, D-254).
    """
    data = load_year(2026).map
    assert [plan.id for plan in data.plans] == [
        "campus",
        "concourse",
        "upper",
        "arena",
        "seaside",
        "expo",
        "job-fair",
    ]
    job_fair = data.plan("job-fair")
    assert job_fair is not None
    assert job_fair.note.startswith("The printed plan shows some tables")
    assert all(not plan.note for plan in data.plans if plan is not job_fair)
    assert data.tour_url == "https://map.concept3d.com/?id=1802"
    assert all(plan.title and plan.subtitle for plan in data.plans)


def test_a_year_without_a_map_file_has_no_plans_or_pins() -> None:
    """2025 bundles no map.toml: it loads with no plans, no pins and no tour."""
    data = load_year(2025).map
    assert (data.plans, data.pins, data.tour_url) == ((), (), "")


@pytest.mark.parametrize("plan", load_year(2026).map.plans, ids=lambda plan: plan.id)
def test_plans_are_webp_within_the_size_budget(plan: Plan) -> None:
    """Each plan is a WebP of at most 2048 px, its recorded size, and within S7's budget.

    A plan larger than that is fitted to 2048 px; the job fair's, cropped to 1700 px
    wide (D-254), keeps its size, as the script never scales up.

    Its thumbnail is the plan fitted to 800 px, with the plan's aspect ratio to the
    pixel's rounding, so a pin's percentages land on the same spot on both (MAP-06).
    """
    image_path, thumb_path = ASSETS_DIR / plan.image, ASSETS_DIR / plan.thumb
    with Image.open(image_path) as image, Image.open(thumb_path) as thumb:
        assert (image.format, thumb.format) == ("WEBP", "WEBP")
        assert image.size == (plan.width, plan.height)
        assert max(image.size) == (1700 if plan.id == "job-fair" else 2048)
        assert max(thumb.size) == 800
        assert abs(thumb.width / thumb.height - image.width / image.height) < 0.005
    assert image_path.stat().st_size <= PLAN_BUDGET
    assert thumb_path.stat().st_size <= THUMB_BUDGET


def test_the_venue_spots_have_pins() -> None:
    """Help & safety's and Venue & hours' places have pins: #372's acceptance list."""
    data = load_year(2026).map
    for key, label, plan in [
        ("info-desk", "Information desk", "concourse"),
        ("registration-desk", "Registration", "concourse"),
        ("quiet-room", "Quiet room", "concourse"),
        ("lost-and-found", "Lost & found", "upper"),
        ("swag-pickup", "Swag pickup", "arena"),
    ]:
        pin = data.pin(key)
        assert pin is not None, key
        assert (pin.label, pin.plan) == (label, plan)


def test_the_venue_spots_are_the_pins_with_a_hyphen() -> None:
    """Search's Places finds 2026's six venue spots and no room pin (D-351)."""
    spots = load_year(2026).map.venue_spots()
    assert [pin.key for pin in spots] == [
        "info-desk",
        "registration-desk",
        "quiet-room",
        "swag-pickup",
        "lost-and-found",
        "staff-office",
    ]


def test_venue_hours_name_their_pins() -> None:
    """Each 2026 venue service with a place shows it on a plan, by its pin key."""
    year = load_year(2026)
    pins = {item.service: item.pin for item in year.content.venue_hours}
    assert pins == {
        "Registration": "registration-desk",
        "Information desk": "info-desk",
        "Swag pickup": "swag-pickup",
        "Quiet room": "quiet-room",
        "Lost & found": "lost-and-found",
        "Luggage check": "",
    }


@pytest.mark.parametrize("source", ["snapshot", "recorded"])
def test_every_2026_feed_room_has_a_pin_or_is_another_location(source: str) -> None:
    """Every room of 2026's feed has a pin unless it is under "Other locations".

    Ionic showed no map for a room its table lacked; here a missing pin fails the
    build (DATA-32). Both the bundled snapshot and the recorded feed are checked.
    """
    year = load_year(2026)
    if source == "snapshot":
        data = process(year.read_snapshot().raw, year.feed_settings)
    else:
        data = processed(2026)
    assert rooms_without_pins(data, year) == []


def tables_off_the_plan(data: ConferenceData, year: YearData) -> list[str]:
    """The feed's job fair tables that have no rectangle on the job fair plan."""
    return sorted(
        {entry.table for entry in job_fair_tables(data)}
        - {table.number for table in year.map.tables}
    )


@pytest.mark.parametrize("source", ["snapshot", "recorded"])
def test_every_2026_feed_table_has_a_rectangle(source: str) -> None:
    """Every job fair table of 2026's feed is marked on the plan (#464).

    A table without one opens the plan saying it isn't there yet; here it fails the
    build, as a room without a pin does.
    """
    year = load_year(2026)
    if source == "snapshot":
        data = process(year.read_snapshot().raw, year.feed_settings)
    else:
        data = processed(2026)
    assert job_fair_tables(data)
    assert tables_off_the_plan(data, year) == []


def test_the_printed_tables_are_t1_to_t20_without_overlaps() -> None:
    """2026's plan prints T1 to T20, each a rectangle no other one overlaps."""
    tables = load_year(2026).map.tables
    assert [table.number for table in tables] == [f"T{n}" for n in range(1, 21)]
    for index, one in enumerate(tables):
        for other in tables[index + 1 :]:
            apart = (
                one.x + one.w <= other.x
                or other.x + other.w <= one.x
                or one.y + one.h <= other.y
                or other.y + other.h <= one.y
            )
            assert apart, (one.number, other.number)


def test_a_new_room_without_a_pin_is_named() -> None:
    """A feed room the registry lacks is reported by name, not silently left mapless."""
    year = load_year(2026)
    data = process(changed(2026, move(142, "Room 999")), year.feed_settings)
    assert rooms_without_pins(data, year) == ["Room 999"]


def test_sprint_rooms_are_the_seaside_rooms_ionic_seeded() -> None:
    """The pins marked for the sprints are Ionic's: a sublabel naming the sprints (MAP-08).

    S-7, the satellite staff office, is not one of them.
    """
    data = load_year(2026).map
    sprint = {pin.key for pin in data.pins if pin.sprint}
    assert sprint == {pin.key for pin in data.pins if "Sprints" in pin.sublabel}
    assert {pin.plan for pin in data.pins if pin.sprint} == {"seaside"}
    assert "s7" not in sprint
    assert len(sprint) == 16


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Room 102A", "102a"),
        ("102A", "102a"),
        ("room 102a", "102a"),
        ("Room 104C", "104c"),  # JavaScript's \s takes a no-break space
        ("Pacific Ballroom - Arena", "pacificballroomarena"),
        ("Pacific Ballroom — Arena", "pacificballroomarena"),
        ("Hall AB", "hallab"),
        ("Expo Hall AB", "expohallab"),
        ("S-3", "s3"),
        ("Roommates", "roommates"),  # "room" only goes with the space after it
        ("", ""),
    ],
)
def test_normalize_room_key_is_ionics(name: str, key: str) -> None:
    """`normalize_room_key` does what Ionic's `normalizeRoomKey` did."""
    assert normalize_room_key(name) == key


def test_the_hall_prefix_finds_the_expo_hall_pin() -> None:
    """`Lunch (Hall AB)` is in Expo Hall AB (D-122), whose pin a bare Hall AB is not.

    The keys differ, so the prefix, applied by feed processing, is what lands the
    lunches on the expo hall's pin; the Arena's hyphen and Ionic's em dash share one.
    """
    data = load_year(2026).map
    assert normalize_room_key("Hall AB") != normalize_room_key("Expo Hall AB")
    assert "Expo Hall AB" in processed(2026).rooms["expo-hall-ab"].name
    pin = data.room_pin("Expo Hall AB")
    assert pin is not None and pin.plan == "arena"
    arena = data.room_pin("Pacific Ballroom - Arena")
    assert arena is not None and arena.label == "Pacific Ballroom — Arena"


@pytest.mark.parametrize("year", YEARS)
def test_room_keys_and_slugs_agree_on_every_feed_room(year: int) -> None:
    """Two feed room names share a pin key exactly when they share a slug.

    So the pins (`normalize_room_key`) and the rooms' routes (`slugify_room`) never
    split one room in two or join two rooms in one.
    """
    names = feed_room_strings(year) | {"Pacific Ballroom - Arena", "Hall AB"}
    by_slug = {slugify_room(name): normalize_room_key(name) for name in names}
    by_key = {normalize_room_key(name): slugify_room(name) for name in names}
    assert len(by_slug) == len(by_key) == len(set(by_slug.values()))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "x = 23.0",
            "x = 123.0",
            r"2026/map.toml: pins\[\d+\]\.x: 123.0 is not between 0 and 100",
        ),
        ("y = 50.0", "y = -1.0", r"pins\[\d+\]\.y: -1.0 is not between 0 and 100"),
        ('plan = "upper"', 'plan = "attic"', r"pins\[\d+\]\.plan: no plan 'attic'"),
        ('key = "102b"', 'key = "102a"', r"pins\[\d+\]\.key: '102a' is listed twice"),
        (
            'key = "info-desk"',
            'key = "Info Desk"',
            r"pins\[0\]\.key: 'Info Desk' is not a-z0-9 words",
        ),
        ('label = "Registration"', 'label = " "', r"pins\[1\]\.label: is empty"),
        ('id = "upper"', 'id = "concourse"', r"plans\[2\]\.id: 'concourse' is listed"),
        ("width = 2048", "width = 0", r"plans\[0\]\.width: must be positive"),
        (
            "maps/2026/upper.webp",
            "maps/2026/upper.png",
            r"plans\[2\]\.image: no file 'maps/2026/upper.png' under src/assets",
        ),
        ("x = 55.0", "x = 55", r"pins\[0\]\.x: expected a number with a decimal"),
        (
            "https://map.concept3d.com",
            "http://map.concept3d.com",
            r"tour_url: expected",
        ),
        ("sprint = true", 'sprint = "yes"', r"pins\[\d+\]\.sprint: expected true or"),
        ('number = "113"', 'number = "112"', r"booths\[1\]\.number: '112' is listed"),
        ('number = "112"', 'number = " "', r"booths\[0\]\.number: is empty"),
        ('number = "112"', "number = 112", r"booths\[0\]\.number: expected"),
        ("x = 0.2365", "x = 1.2365", r"booths\[0\]\.x: 1.2365 is not between 0 and 1"),
        ("h = 0.0912", "h = -0.1", r"booths\[0\]\.h: -0.1 is not between 0 and 1"),
        ("w = 0.0473", "w = 0.0", r"booths\[0\]\.w: must be positive"),
        (
            "x = 0.2365",
            "x = 0.9600",
            r"booths\[0\]\.w: x \+ w is 1.0073, past the plan",
        ),
        (
            "y = 0.6965",
            "y = 0.9500",
            r"booths\[0\]\.h: y \+ h is 1.0412, past the plan",
        ),
        ('label = "Attendee lounge"', 'label = " "', r"booths\[\d+\]\.label: is empty"),
        ('id = "expo"', 'id = "hall"', r"2026/map.toml: booths: no plan 'expo' to put"),
        ('note = "The printed', 'note = " " # "', r"plans\[6\]\.note: is empty"),
        ('number = "T8"', 'number = "T7"', r"tables\[7\]\.number: 'T7' is listed"),
        (
            'number = "T1"\nx = 0.0765',
            'number = "T1"\nx = 1.0765',
            r"2026/map.toml: tables\[0\]\.x: 1.0765 is not between 0 and 1",
        ),
        ('id = "job-fair"', 'id = "jobs"', r"tables: no plan 'job-fair' to put them"),
    ],
)
def test_a_bad_map_entry_names_file_entry_and_field(
    data_dir: Path, old: str, new: str, message: str
) -> None:
    """A broken map.toml fails to load with the file, the entry and the field."""
    edit(data_dir / "2026" / "map.toml", old, new)
    with pytest.raises(YearDataError, match=message):
        load_year(2026, data_dir)


def test_a_venue_service_must_name_a_pin_that_exists(data_dir: Path) -> None:
    """A venue service's pin that map.toml lacks fails in content.toml's name."""
    # "\npin": the service's own key, not [help]'s quiet_room_pin.
    edit(data_dir / "2026" / "content.toml", '\npin = "quiet-room"', '\npin = "spa"')
    with pytest.raises(
        YearDataError,
        match=r"2026/content.toml: venue_hours\[3\].pin: no pin 'spa' in map.toml",
    ):
        load_year(2026, data_dir)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'quiet_room_pin = "quiet-room"',
            'quiet_room_pin = "spa"',
            r"2026/content.toml: help.quiet_room_pin: no pin 'spa' in map.toml",
        ),
        (
            'info_desk_pin = "info-desk"',
            'info_desk_pin = " "',
            r"2026/content.toml: help.info_desk_pin: is empty",
        ),
    ],
    ids=["unknown", "blank"],
)
def test_help_s_places_must_name_pins_that_exist(
    data_dir: Path, old: str, new: str, message: str
) -> None:
    """A Help & safety place's pin that map.toml lacks, or a blank one, fails to load."""
    edit(data_dir / "2026" / "content.toml", old, new)
    with pytest.raises(YearDataError, match=message):
        load_year(2026, data_dir)
