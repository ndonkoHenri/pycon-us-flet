"""The year's floor plans and the pins on them, from `map.toml` (D-45, DATA-32, MAP-07).

`map.toml` replaces Ionic's `ROOM_LOCATIONS` and `VENUE_LOCATIONS`: a `[[plans]]`
table of the venue's floor plans (images bundled under `src/assets/`, D-312), a
`[[pins]]` table of the spots marked on them, rooms and venue spots alike, a
`[[booths]]` table of the expo's booths on the `expo` plan (EXPO-02, D-254), and the
venue's 3D tour. The `job-fair` plan heads the Map's Job fair pane, with its `note`,
and a `[[tables]]` table marks its printed tables (#464). `config.load_year()` builds
it into `MapData` through
`year_schema` and checks it with `check_map()`; `YearData.map` holds it, and
`MapData.room_pin()` finds a feed room's pin by `normalize_room_key()`. A year
without the file has no plans and no pins. Whether every feed room has a pin is a test
over the year's snapshot (`tests/test_year_map.py`), since the app never parses the
snapshot just to check it (D-38); so are the expo's gaps, the booths without an
exhibitor and the exhibitors without a booth on the plan (`core/expo.py`), and the
feed's job fair tables without a rectangle.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pycon_us.core.hours import ServiceHours
from pycon_us.core.slugs import normalize_room_key
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
"""`src/assets/`, which a plan's `image` and `thumb` are relative to.

`flet build` bundles `src/` whole, so the files are there on the phone too, and it
is the app's assets folder (`ft.run`'s default `assets_dir`, next to `main.py`).
"""

EXPO_PLAN = "expo"
"""The id of the plan the booths are on: a year with booths has a plan of this id."""

JOB_FAIR_PLAN = "job-fair"
"""The id of the job fair's plan: the Map's Job fair pane and its card (MAP-04, D-254)."""

_PIN_KEY = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


@dataclass(frozen=True)
class Plan:
    """One floor plan, a `[[plans]]` entry.

    Attributes:
        id: Its id, unique in the year: the route's `plan/<id>` (decisions §M).
        title: Its name ("Concourse level").
        image: The plan, relative to `src/assets/`: at most 2048 px on its longer
            side, lossy WebP (D-312).
        thumb: Its thumbnail, relative to `src/assets/`: the plan fitted to 800 px,
            so a pin's percentages land on the same spot.
        width: The plan image's width in pixels; with `height`, its aspect ratio and
            the floor viewer's maximum zoom (D-312).
        height: The plan image's height in pixels.
        subtitle: What is on it ("Tutorials, talk tracks, registration"); empty
            without one.
        note: What the plan's list should be read with, shown under the job fair's
            card and never in the viewer (D-254); empty without one.
    """

    id: str
    title: str
    image: str
    thumb: str
    width: int
    height: int
    subtitle: str = ""
    note: str = ""


@dataclass(frozen=True)
class Pin:
    """One spot on a floor plan, a `[[pins]]` entry: a room or a venue spot.

    Attributes:
        key: Its key, unique in the year: a room's is `normalize_room_key()` of its
            feed name (`103abc`); a venue spot's has a `-` (`info-desk`), so it is
            never a room's.
        label: Its name ("Room 103", "Information desk").
        plan: The id of the plan it is on.
        x: Its distance from the plan's left edge, in percent of the width.
        y: Its distance from the plan's top edge, in percent of the height.
        sublabel: What happens there ("Talk track / Security track"); empty without one.
        sprint: Whether the sprints use the room (MAP-08).
    """

    key: str
    label: str
    plan: str
    x: float
    y: float
    sublabel: str = ""
    sprint: bool = False


@dataclass(frozen=True)
class Booth:
    """One booth on the expo plan, a `[[booths]]` entry: a rectangle to tap (D-312).

    The rectangle is in ratios of the plan, so it lands on the image at any size.

    Attributes:
        number: Its number as the feed's `booth_number` writes it ("613"), unique in
            the year; numbers compare as text, never as integers.
        x: Its left edge's distance from the plan's left edge, as a ratio of the width.
        y: Its top edge's distance from the plan's top edge, as a ratio of the height.
        w: Its width, as a ratio of the plan's width.
        h: Its height, as a ratio of the plan's height.
        label: The name of a booth the feed gives no exhibitor ("Attendee lounge",
            D-254); empty for the others, which their sponsors name.
    """

    number: str
    x: float
    y: float
    w: float
    h: float
    label: str = ""


@dataclass(frozen=True)
class Table:
    """One printed job fair table on the `job-fair` plan, a `[[tables]]` entry (#464).

    A rectangle in ratios of the plan, as a booth's, that `plan/job-fair?table=T8`
    selects; who is at it comes from the feed (`Sponsor.job_fair_table`), never from
    here, since the print and the feed disagree (D-254).

    Attributes:
        number: Its number as the feed's `job_fair_table_number` writes it ("T8"),
            unique in the year.
        x: Its left edge's distance from the plan's left edge, as a ratio of the width.
        y: Its top edge's distance from the plan's top edge, as a ratio of the height.
        w: Its width, as a ratio of the plan's width.
        h: Its height, as a ratio of the plan's height.
    """

    number: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class MapData:
    """The year's `map.toml`: its floor plans, its pins and the 3D tour.

    Attributes:
        plans: The floor plans, in the Map's order (MAP-02).
        pins: The rooms and venue spots marked on them.
        booths: The expo's booths, on the `expo` plan; empty for a year without.
        tables: The job fair's tables, on the `job-fair` plan; empty for a year
            without.
        tour_url: The venue's 3D tour, opened as a link (MAP-03); empty without one.
    """

    plans: tuple[Plan, ...] = ()
    pins: tuple[Pin, ...] = ()
    booths: tuple[Booth, ...] = ()
    tables: tuple[Table, ...] = ()
    tour_url: str = ""

    def plan(self, plan_id: str) -> Plan | None:
        """Return the plan whose id is `plan_id`, or None.

        Args:
            plan_id: A route's `plan/<id>` segment.
        """
        return next((plan for plan in self.plans if plan.id == plan_id), None)

    def table(self, number: str) -> Table | None:
        """Return the job fair table numbered `number` ("T8"), or None.

        Args:
            number: A table as the feed writes it, or a route's `?table=` value.
        """
        return next((table for table in self.tables if table.number == number), None)

    def pin(self, key: str) -> Pin | None:
        """Return the pin whose key is `key`, or None.

        Args:
            key: A pin key: a room's `normalize_room_key()`, or a venue spot's
                (`info-desk`, as `content.toml`'s venue hours name it).
        """
        return next((pin for pin in self.pins if pin.key == key), None)

    def venue_spots(self) -> tuple[Pin, ...]:
        """Return the pins that are venue spots, not rooms, in the file's order.

        A venue spot's key has a `-` (`info-desk`), which `normalize_room_key()`
        never leaves in a room's: what search's Places scope finds besides the feed's
        rooms (D-351). A room's pin is found through its feed room instead, and a room
        pin no feed room names (a part of a joined room) is not a place to search.
        """
        return tuple(pin for pin in self.pins if "-" in pin.key)

    def floors(self) -> tuple[tuple[str, frozenset[str]], ...]:
        """Return each plan's title and the keys of the pins on it, in the Map's order.

        What `rooms.room_list()` groups the Rooms list by (ROOM-01): a room is on the
        floor of its pin.
        """
        return tuple(
            (plan.title, frozenset(pin.key for pin in self.pins if pin.plan == plan.id))
            for plan in self.plans
        )

    def room_pin(self, room: str) -> Pin | None:
        """Return the pin of a room, found by `normalize_room_key()`, or None.

        Args:
            room: The room's name as the feed writes it ("Room 104C", "104C").
        """
        return self.pin(normalize_room_key(room))


def check_map(data: MapData, file: str) -> None:
    """Check the rules of `map.toml` that its types cannot say.

    Plans: unique ids, a title, a note that is not blank when given, a positive size,
    and image and thumbnail files that exist. Pins: unique keys of `a-z0-9` words
    joined by `-`, a label, a plan that exists, and a position within the plan (0 to
    100 percent). Booths: an `expo` plan to be on, unique numbers that are not blank,
    a label that is not blank when given, and a rectangle inside the plan (ratios from
    0 to 1, a positive size, `x + w` and `y + h` at most 1). Tables: the same, on
    a `job-fair` plan, without labels. The tour: `https`.

    Args:
        data: The year's map data.
        file: The file's name in error messages (`2026/map.toml`).

    Raises:
        YearDataError: An entry breaks a rule; the message names the file, the entry
            and the field (`2026/map.toml: pins[3].x: 120.0 is not between 0 and 100`).
    """
    _check_plans_and_pins(data, file)
    _check_areas(data.booths, "booths", EXPO_PLAN, data, file)
    for index, booth in enumerate(data.booths):
        if booth.label:
            check_text(booth.label, file, f"booths[{index}].label")
    _check_areas(data.tables, "tables", JOB_FAIR_PLAN, data, file)


def _check_plans_and_pins(data: MapData, file: str) -> None:
    """Check the tour, the plans and the pins (`check_map()`'s first half)."""
    if data.tour_url:
        check_https(data.tour_url, file, "tour_url")
    plan_ids: set[str] = set()
    for index, plan in enumerate(data.plans):
        key = f"plans[{index}]"
        check_text(plan.id, file, f"{key}.id")
        if plan.id in plan_ids:
            raise YearDataError(f"{file}: {key}.id: {plan.id!r} is listed twice")
        plan_ids.add(plan.id)
        check_text(plan.title, file, f"{key}.title")
        if plan.note:
            check_text(plan.note, file, f"{key}.note")
        for field in ("width", "height"):
            if getattr(plan, field) <= 0:
                raise YearDataError(f"{file}: {key}.{field}: must be positive")
        for field in ("image", "thumb"):
            path = getattr(plan, field)
            if not (ASSETS_DIR / path).is_file():
                raise YearDataError(
                    f"{file}: {key}.{field}: no file {path!r} under src/assets"
                )
    keys: set[str] = set()
    for index, pin in enumerate(data.pins):
        key = f"pins[{index}]"
        if not _PIN_KEY.fullmatch(pin.key):
            raise YearDataError(
                f"{file}: {key}.key: {pin.key!r} is not a-z0-9 words joined by '-'"
            )
        if pin.key in keys:
            raise YearDataError(f"{file}: {key}.key: {pin.key!r} is listed twice")
        keys.add(pin.key)
        check_text(pin.label, file, f"{key}.label")
        if pin.plan not in plan_ids:
            raise YearDataError(f"{file}: {key}.plan: no plan {pin.plan!r}")
        for field in ("x", "y"):
            value = getattr(pin, field)
            if not 0 <= value <= 100:
                raise YearDataError(
                    f"{file}: {key}.{field}: {value} is not between 0 and 100"
                )


def _check_areas(
    areas: tuple[Booth, ...] | tuple[Table, ...],
    field: str,
    plan_id: str,
    data: MapData,
    file: str,
) -> None:
    """Check the booths or the tables: their plan, their numbers and their rectangles.

    Args:
        areas: `data.booths` or `data.tables`.
        field: Their table's name in `map.toml` (`booths`), for the messages.
        plan_id: The plan they are on, which must exist when there are any.
        data: The year's map data.
        file: The file's name in error messages.
    """
    if areas and data.plan(plan_id) is None:
        raise YearDataError(f"{file}: {field}: no plan {plan_id!r} to put them on")
    numbers: set[str] = set()
    for index, area in enumerate(areas):
        key = f"{field}[{index}]"
        check_text(area.number, file, f"{key}.number")
        if area.number in numbers:
            raise YearDataError(
                f"{file}: {key}.number: {area.number!r} is listed twice"
            )
        numbers.add(area.number)
        for name in ("x", "y", "w", "h"):
            value = getattr(area, name)
            if not 0 <= value <= 1:
                raise YearDataError(
                    f"{file}: {key}.{name}: {value} is not between 0 and 1"
                )
        for name in ("w", "h"):
            if getattr(area, name) <= 0:
                raise YearDataError(f"{file}: {key}.{name}: must be positive")
        for start, size in (("x", "w"), ("y", "h")):
            end = getattr(area, start) + getattr(area, size)
            if end > 1:
                raise YearDataError(
                    f"{file}: {key}.{size}: {start} + {size} is {end:g}, past the plan"
                )


def check_hours_pins(hours: Iterable[ServiceHours], data: MapData, file: str) -> None:
    """Refuse a venue service whose `pin` names no pin of `map.toml`.

    Args:
        hours: The year's `venue_hours` (`content.toml`).
        data: The year's map data.
        file: The file the hours come from, for the message (`2026/content.toml`).

    Raises:
        YearDataError: A `pin` is not a key of `data.pins`.
    """
    check_pin_keys(
        ((f"venue_hours[{index}].pin", item.pin) for index, item in enumerate(hours)),
        data,
        file,
    )


def check_pin_keys(keys: Iterable[tuple[str, str]], data: MapData, file: str) -> None:
    """Refuse a pin key, given where it is written, that names no pin of `map.toml`.

    Args:
        keys: Each key's field and the key, an empty key standing for no pin:
            `("help.quiet_room_pin", "quiet-room")` (`HelpInfo.pin_keys()`).
        data: The year's map data.
        file: The file the keys come from, for the message (`2026/content.toml`).

    Raises:
        YearDataError: A key is not a key of `data.pins`.
    """
    for where, key in keys:
        if key and data.pin(key) is None:
            raise YearDataError(f"{file}: {where}: no pin {key!r} in map.toml")
