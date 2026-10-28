"""A reminder tap lands where its route says, with the root below (#450, D-21, D-396).

A reminder's payload is its route (``services/reminders.py``), and a tap opens it as a
link does: cold, ``Start`` opens it (``test_routes_locations.py``); warm, it is a route
change. Here, every route the 2026 plan can produce names a page the app has, and the
routes render in the app's own Views (``tests/links.py``): a session over My schedule,
whose Back goes to My schedule, then Now; a session removed from the feed shows its
not-found state over My schedule; a conference moment opens its own page.
"""

from datetime import datetime
from urllib.parse import unquote, urlparse

import pytest

from pycon_us.locations import DRILL_KINDS, PAGES
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services.reminder_plan import MAX_PENDING, plan
from pycon_us.year_moments import keynote_moments
from tests import links
from tests.links import DATA, EXIT, YEAR, Open

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)

TALK = "142"
"""A 2026 talk: Saturday 16 May at 10:30 AM in Grand Ballroom A."""

BEFORE = datetime(2026, 5, 1, 9, 0, tzinfo=YEAR.conference.zone)
"""A fixed now before PyCon US 2026 starts: every session and moment is ahead."""


def page_of(route: str) -> str:
    """Return the page a route's drill pairs stand on, checking each pair's id.

    Every pair must be a session the feed has: the only kind a reminder pushes.
    """
    parts = urlparse(route).path.strip("/").split("/")
    while len(parts) >= 3 and parts[-2] in DRILL_KINDS:
        kind, ident = parts[-2], unquote(parts[-1])
        assert kind == "session" and ident in DATA.sessions, route
        parts = parts[:-2]
    return "/" + "/".join(parts)


def every_route() -> set[str]:
    """Every route the 2026 plan can hold: each session saved, every moment on.

    ``plan()`` keeps the ``MAX_PENDING`` soonest, so the sessions are saved a batch
    at a time; each batch's plan must hold a reminder for each of them.
    """
    zone = YEAR.conference.zone
    moments = (
        *YEAR.content.event_reminders,
        *keynote_moments(DATA, YEAR.content.keynotes, zone, use_24h=False),
    )
    settings = ReminderSettings(session_lead=10)
    ids = sorted(DATA.sessions)
    batch = MAX_PENDING // 2  # room for the moments that come sooner
    routes = set()
    for start in range(0, len(ids), batch):
        saved = ids[start : start + batch]
        reminders = plan(DATA, saved, settings, (), BEFORE, zone=zone, use_24h=False)
        assert len(reminders) == len(saved)
        routes |= {r.route for r in reminders}
    every_moment = plan(DATA, [], settings, moments, BEFORE, zone=zone, use_24h=False)
    assert len(every_moment) == len(moments)
    return routes | {r.route for r in every_moment}


def test_every_route_the_2026_plan_produces_names_a_page_the_app_has() -> None:
    """Each reminder's route is a page, or sessions the feed has pushed on one."""
    routes = every_route()
    assert len(routes) > len(DATA.sessions)  # the moments' pages came too
    assert {page_of(route) for route in routes} <= PAGES


async def test_a_session_reminder_opens_the_session_over_my_schedule(
    open_at: Open,
) -> None:
    """The session over My schedule; Back goes to My schedule, then Now, then out."""
    route = f"/my-schedule/session/{TALK}"
    shown = await open_at(route)
    assert shown.routes() == ["/", route]
    assert shown.has("session.title")
    assert [await shown.back() for _ in range(3)] == ["/my-schedule", "/now", EXIT]


async def test_a_warm_tap_builds_the_same_stack(open_at: Open) -> None:
    """From anywhere, a tap's route change builds the session over My schedule."""
    shown = await open_at("/map/room/grand-ballroom-a")
    await shown.go(f"/my-schedule/session/{TALK}")
    assert shown.routes() == ["/", f"/my-schedule/session/{TALK}"]
    assert await shown.back() == "/my-schedule"


async def test_a_removed_session_shows_its_not_found_state_over_my_schedule(
    open_at: Open,
) -> None:
    """A reminder for a session the feed has dropped since: not found, Back to the list."""
    route = "/my-schedule/session/999999"
    assert "999999" not in DATA.sessions
    shown = await open_at(route)
    assert shown.routes() == ["/", route]
    assert shown.has("session.not_found")
    assert await shown.back() == "/my-schedule"


@pytest.mark.parametrize("category", ["lightning", "open_space", "keynote"])
async def test_a_moment_opens_its_own_page(open_at: Open, category: str) -> None:
    """A sign-up opens its page, a keynote its session, each over its root (D-274)."""
    zone = YEAR.conference.zone
    moments = (
        *YEAR.content.event_reminders,
        *keynote_moments(DATA, YEAR.content.keynotes, zone, use_24h=False),
    )
    route = next(m.route for m in moments if m.category == category)
    shown = await open_at(route)
    assert shown.routes()[-1] in {route, "/"}  # a More page, or a session pushed
    assert not shown.has("app.not_found")
    assert not shown.has("session.not_found")
