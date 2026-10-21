"""The year's floor plans and the pins on them, from ``map.toml`` (D-45, DATA-32, MAP-07).

``map.toml`` replaces Ionic's ``ROOM_LOCATIONS`` and ``VENUE_LOCATIONS``: a ``[[plans]]``
table of the venue's floor plans (images bundled under ``src/assets/``, D-312), a
``[[pins]]`` table of the spots marked on them, rooms and venue spots alike, and the
venue's 3D tour. ``config.load_year()`` builds it into ``MapData`` through
``year_schema`` and checks it with ``check_map()``; ``YearData.map`` holds it, and
``MapData.room_pin()`` finds a feed room's pin by ``normalize_room_key()``. A year
without the file has no plans and no pins. Whether every feed room has a pin is a test
over the year's snapshot (``tests/test_year_map.py``), since the app never parses the
snapshot just to check it (D-38).
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
"""``src/assets/``, which a plan's ``image`` and ``thumb`` are relative to.

``flet build`` bundles ``src/`` whole, so the files are there on the phone too, and it
is the app's assets folder (``ft.run``'s default ``assets_dir``, next to ``main.py``).
"""

_PIN_KEY = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


@dataclass(frozen=True)
class Plan:
    """One floor plan, a ``[[plans]]`` entry.

    Attributes:
        id: Its id, unique in the year: the route's ``plan/<id>`` (decisions §M).
        title: Its name ("Concourse level").
        image: The plan, relative to ``src/assets/``: at most 2048 px on its longer
            side, lossy WebP (D-312).
        thumb: Its thumbnail, relative to ``src/assets/``: the plan fitted to 800 px,
            so a pin's percentages land on the same spot.
        width: The plan image's width in pixels; with ``height``, its aspect ratio and
            the floor viewer's maximum zoom (D-312).
        height: The plan image's height in pixels.
        subtitle: What is on it ("Tutorials, talk tracks, registration"); empty
            without one.
    """

    id: str
    title: str
    image: str
    thumb: str
    width: int
    height: int
    subtitle: str = ""


@dataclass(frozen=True)
class Pin:
    """One spot on a floor plan, a ``[[pins]]`` entry: a room or a venue spot.

    Attributes:
        key: Its key, unique in the year: a room's is ``normalize_room_key()`` of its
            feed name (``103abc``); a venue spot's has a ``-`` (``info-desk``), so it is
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
class MapData:
    """The year's ``map.toml``: its floor plans, its pins and the 3D tour.

    Attributes:
        plans: The floor plans, in the Map's order (MAP-02).
        pins: The rooms and venue spots marked on them.
        tour_url: The venue's 3D tour, opened as a link (MAP-03); empty without one.
    """

    plans: tuple[Plan, ...] = ()
    pins: tuple[Pin, ...] = ()
    tour_url: str = ""

    def plan(self, plan_id: str) -> Plan | None:
        """Return the plan whose id is ``plan_id``, or None.

        Args:
            plan_id: A route's ``plan/<id>`` segment.
        """
        return next((plan for plan in self.plans if plan.id == plan_id), None)

    def pin(self, key: str) -> Pin | None:
        """Return the pin whose key is ``key``, or None.

        Args:
            key: A pin key: a room's ``normalize_room_key()``, or a venue spot's
                (``info-desk``, as ``content.toml``'s venue hours name it).
        """
        return next((pin for pin in self.pins if pin.key == key), None)

    def room_pin(self, room: str) -> Pin | None:
        """Return the pin of a room, found by ``normalize_room_key()``, or None.

        Args:
            room: The room's name as the feed writes it ("Room 104C", "104C").
        """
        return self.pin(normalize_room_key(room))


def check_map(data: MapData, file: str, assets_dir: Path = ASSETS_DIR) -> None:
    """Check the rules of ``map.toml`` that its types cannot say.

    Plans: unique ids, a title, a positive size, and image and thumbnail files that
    exist. Pins: unique keys of ``a-z0-9`` words joined by ``-``, a label, a plan that
    exists, and a position within the plan (0 to 100 percent). The tour: ``https``.

    Args:
        data: The year's map data.
        file: The file's name in error messages (``2026/map.toml``).
        assets_dir: Where the plans' paths start.

    Raises:
        YearDataError: An entry breaks a rule; the message names the file, the entry
            and the field (``2026/map.toml: pins[3].x: 120.0 is not between 0 and 100``).
    """
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
        for field in ("width", "height"):
            if getattr(plan, field) <= 0:
                raise YearDataError(f"{file}: {key}.{field}: must be positive")
        for field in ("image", "thumb"):
            path = getattr(plan, field)
            if not (assets_dir / path).is_file():
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


def check_hours_pins(hours: Iterable[ServiceHours], data: MapData, file: str) -> None:
    """Refuse a venue service whose ``pin`` names no pin of ``map.toml``.

    Args:
        hours: The year's ``venue_hours`` (``content.toml``).
        data: The year's map data.
        file: The file the hours come from, for the message (``2026/content.toml``).

    Raises:
        YearDataError: A ``pin`` is not a key of ``data.pins``.
    """
    for index, item in enumerate(hours):
        if item.pin and data.pin(item.pin) is None:
            raise YearDataError(
                f"{file}: venue_hours[{index}].pin: no pin {item.pin!r} in map.toml"
            )
