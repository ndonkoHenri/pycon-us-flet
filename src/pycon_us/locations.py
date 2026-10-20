"""The app's locations: drill links, Back targets and view options.

A location is a route path, with an optional query of view options (decisions §M):
``/schedule/session/42/speaker/17?highlight=99``. The helpers here are pure, so they are
unit-tested on every route shape, apart from the ``use_query()`` hook. Screens import
them without importing the route table, which imports the screens (D-164):
``routes.py`` holds the table itself, and a test keeps its pages and ``PAGES`` the same.
"""

from urllib.parse import parse_qsl, quote, urlparse

import flet as ft

from pycon_us.year_tracks import HUB_PAGES

TAB_ROOTS = ("/now", "/schedule", "/my-schedule", "/map", "/more")
"""The five tab roots, in the bottom bar's order (D-13)."""

DRILL_KINDS = ("session", "speaker", "room", "sponsor", "plan")
"""The drill's segment pairs, ``<kind>/<id>``, one pushed View each (D-17, D-141)."""

PAGES = frozenset(
    {
        *TAB_ROOTS,
        "/search",
        "/more/speakers",
        "/more/tracks",
        *(f"/more/tracks/{segment}" for segment in HUB_PAGES),
        "/more/keynotes",
        "/more/open-spaces",
        "/more/lightning-talks",
        "/more/sprints",
        "/more/sponsors",
        "/more/app",
        "/more/developer",
        "/more/wifi",
        "/more/psf",
    }
)
"""Every page path without a parameter: the places Back can walk up to (D-19).

``/more/tracks/<slug>`` is a page too, but nothing below it walks up to it except
through a drill pair, so only its parent needs to be here.
"""


def drill_href(view_path: str, kind: str, ident: str) -> str:
    """Return the location that pushes one detail level on top of a View.

    Args:
        view_path: The View's own path (``ft.use_view_path()``), never ``page.route``,
            so a detail opens on top of the View that links to it, under any root.
        kind: One of ``DRILL_KINDS``.
        ident: The session or speaker id, room or sponsor slug, or plan id. It is quoted
            whole (D-42), so ``/``, ``:``, ``+``, spaces and non-ASCII stay inside one
            segment; ``Drill`` unquotes it.

    Returns:
        The location, e.g. ``/now/session/poster%20detail%2B1``.
    """
    return f"{view_path.rstrip('/')}/{kind}/{quote(ident, safe='')}"


def parent_of(location: str, search_base: str = "/now") -> str:
    """Return where Back goes from a location (D-19): one step, never more.

    Drop the last drill pair; else walk up to the nearest page, so ``/more/staff/lead``
    returns ``/more`` because ``/more/staff`` is not a page. ``/search`` returns to
    ``search_base``, the location (query included) it was opened from. A tab root
    returns ``/``, the start route. The query is dropped: view options do not survive
    Back (decisions §M).

    Args:
        location: The popped View's route, or any location.
        search_base: ``ViewMemory.search_base``.

    Returns:
        The parent location.
    """
    parts = urlparse(location).path.strip("/").split("/")
    if parts == ["search"]:
        return search_base
    if len(parts) >= 3 and parts[-2] in DRILL_KINDS:
        return "/" + "/".join(parts[:-2])
    parent = parts[:-1]
    while parent and "/" + "/".join(parent) not in PAGES:
        parent.pop()
    return "/" + "/".join(parent)


def start_target(last_location: str, search_base: str) -> str:
    """Return where the start route ``/`` sends a session (D-143).

    A new session in the same process returns to where the user was. A location under
    ``/search`` cannot be rebuilt over its opener (a fresh Router puts a global modal
    over ``/``), so it returns to the opener instead. P2 adds ``/welcome`` on first run.

    Args:
        last_location: ``ViewMemory.last_location``; empty before any screen showed.
        search_base: ``ViewMemory.search_base``.

    Returns:
        The location to navigate to.
    """
    if not last_location:
        return "/now"
    if urlparse(last_location).path.split("/")[1] == "search":
        return search_base
    return last_location


def query_of(location: str) -> dict[str, str]:
    """Return a location's view options, the query (decisions §M; U9 interim).

    Args:
        location: A location such as ``/search?scope=rooms``.

    Returns:
        Each option once, its last value winning; blank values are kept as ``""``.
    """
    return dict(parse_qsl(urlparse(location).query, keep_blank_values=True))


def is_top_view(location: str, view_path: str) -> bool:
    """Return whether a location addresses this View, so it is the top one (D-164).

    Compare with ``page.route``, never ``ft.use_route_location()``: under a global
    modal the Router renders the Views below it at the remembered opener's location,
    so the opener's View would pass that test too (``/map`` under
    ``/search?scope=rooms``), and so would ``Start`` under a modal entered directly.

    Args:
        location: The addressed location, ``page.route``, query included.
        view_path: The View's own path, ``ft.use_view_path()``.

    Returns:
        True only for the View the location's path ends at.
    """
    return (urlparse(location).path.rstrip("/") or "/") == view_path


def use_query() -> dict[str, str]:
    """Return the view options of the location that opened this View (U9 interim).

    Read once, when the View mounts, and only by the View the location addresses
    (``is_top_view()``): a deep entry builds the Views below it too, and a global
    modal keeps its opener's Views mounted below it; the query is not theirs. Options
    that must survive Back live in ``ViewMemory`` (D-18); the query only seeds them.

    Returns:
        The options, as ``query_of()`` reads them; empty for a View below the top.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    query, _ = ft.use_state(
        lambda: query_of(page.route) if is_top_view(page.route, view_path) else {}
    )
    return query
