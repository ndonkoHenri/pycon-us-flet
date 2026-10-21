"""``ViewMemory``: where the user left the app, for the whole Python process (D-18, D-143).

It is plain, not a store: writing it re-renders nothing, and it has no context or hook.
``main.py`` creates the process's one ``ViewMemory``, and screens reach it through
``Services.memory`` (D-231).
"""

from dataclasses import dataclass, field, fields
from datetime import date
from random import Random

from pycon_us.core.list_place import Place


@dataclass
class ViewMemory:
    """Where the user left the app, kept for the whole Python process (D-18, D-143).

    Plain, not observable: writing it re-renders nothing. ``main.py`` creates one at
    import and every session's ``App`` gets that one, so a new session in the same
    process (an Android activity recreation, F26, or a relaunch after Back on Now, F29)
    finds it as the user left it. Fields join with the screens that remember something
    (the Schedule's day and offsets; the search query and scope from P1).

    Attributes:
        last_location: The top View's route, where the start route returns a new
            session (D-143, #74); empty until a screen records it.
        search_base: The location, query included, that opened ``/search``; Back from
            search returns there (D-19). The opener records it.
        schedule_day: The day the Schedule shows; None until the user picks one, so
            the Schedule opens on today during the conference (SCHED-01).
        schedule_offsets: Each day list's scroll offset when its last scroll ended,
            in logical pixels: the Schedule puts it back when the list shows again.
        schedule_places: Each day list's place, the item at its top and how far into
            it, which the Schedule puts back after a text-size change (D-331).
        schedule_basis: The text and list widths and the time's position the
            places were measured with; a change makes their offsets stale (D-331).
        jumped_on: The conference day on which the Schedule last jumped to now: it
            jumps by itself on the first display of each today in this process, and
            not again that day, a "Now" tap included (D-18, D-155, D-204).
        search_query: What is typed in the search field; an opener clears it, so
            each search starts empty (D-193).
        search_scope: The search's scope, one of ``core.search.SCOPES``, for a Search
            View that mounts without its ``?scope=`` (a deep entry below a result).
        map_tab: The Map's pane, a ``screens.map.PANES`` slug; ``?tab=`` seeds it
            (MAP-01).
        map_offsets: Each Map pane's scroll offset when its last scroll ended, by
            slug, in logical pixels: the Map puts it back when the pane shows again.
        map_zooms: Each Map plan pane's last transform, by slug, as the viewer
            reported it: scale, then the translation in logical pixels. The pane puts
            it back when it shows again (D-312).
        expo_booth: The number of the booth selected on the expo plan; empty for
            none. The Expo pane and ``…/plan/expo`` share it (EXPO-01).
        room_highlights: The session each mounted room View has highlighted, by its
            View path (ROOM-03): a View rebuilt in a new session from the same
            location (D-143) finds its own and neither scrolls nor lights up again
            (D-18). The View removes its entry when it leaves, so the next room tile
            highlights again.
        plan_pins: The pin each mounted floor viewer shows, by its View path (D-143):
            ``?pin=`` seeds it, and a View rebuilt in a new session from the same
            location finds it and does not pulse the pin again (D-18, D-34). The
            View removes its entry when it leaves, so the next opening pulses.
        spotlight: The slug of the sponsor Now's spotlight thanks: picked once for
            the process, so a relaunch after Back on Now (F29) shows the same one,
            and picked again only when it leaves the feed (D-298).
        rng: Where the spotlight's pick comes from; a test gives a seeded one. It is
            left out of comparisons, as two ``Random``s are never equal.
    """

    last_location: str = ""
    search_base: str = "/now"
    schedule_day: date | None = None
    schedule_offsets: dict[date, float] = field(default_factory=dict)
    schedule_places: dict[date, Place] = field(default_factory=dict)
    schedule_basis: tuple[float, float, bool] | None = None
    jumped_on: date | None = None
    search_query: str = ""
    search_scope: str = "all"
    map_tab: str = "rooms"
    map_offsets: dict[str, float] = field(default_factory=dict)
    map_zooms: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    expo_booth: str = ""
    room_highlights: dict[str, str] = field(default_factory=dict)
    plan_pins: dict[str, str] = field(default_factory=dict)
    spotlight: str = ""
    rng: Random = field(default_factory=Random, compare=False)

    def reset(self) -> None:
        """Forget where the user was, as after a fresh install (Reset app, D-198).

        Every field returns to its default, so the Schedule opens on today and jumps
        to now again, and a new session starts on Now.
        """
        fresh = ViewMemory()
        for each in fields(self):
            setattr(self, each.name, getattr(fresh, each.name))
