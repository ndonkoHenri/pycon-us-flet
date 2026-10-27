"""The Views the Router stacks for a location, for the route tests (#623).

``test_routes.py`` (the route table) and ``test_routes_locations.py`` (Back, links,
view options, the top View and the start route) read a location's levels with the
Router's own matcher (``_match_routes`` and ``_split_chain_into_view_levels`` in
``flet/components/router.py``, internal), so a Flet bump that changes matching fails
there first.
"""

from urllib.parse import unquote

from flet.components.router import _match_routes, _split_chain_into_view_levels

from pycon_us.routes import ROUTES

type Level = tuple[str, str, dict[str, str]]


def view_levels(location: str) -> list[Level]:
    """Each View the Router stacks for location: its screen, path and own params.

    The Router gives a level the params accumulated up to it, so a drill level's
    ``kind`` and ``ident`` are its own pair's (F6).
    """
    chain = _match_routes(ROUTES, location)
    assert chain is not None, f"no route matches {location}"
    _, entries = _split_chain_into_view_levels(chain)
    levels = []
    for match, _ in entries:
        params: dict[str, str] = {}
        for m in chain[: chain.index(match) + 1]:
            params.update(m.params)
        screen = match.route.component
        assert screen is not None  # a View level always has a component
        levels.append((screen.__name__, match.resolved_path, params))
    return levels


def drill_params(location: str) -> list[tuple[str, str]]:
    """The (kind, unquoted id) each drill level of location sees, in order."""
    return [
        (params["kind"], unquote(params["ident"]))
        for name, _, params in view_levels(location)
        if name == "Drill"
    ]
