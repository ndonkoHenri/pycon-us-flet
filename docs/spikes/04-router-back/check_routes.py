"""Host checks for the S4 route table: per-level params, Back targets and depths.

Run from this folder with `uv run python check_routes.py`. It matches locations
with the Router's own matcher (`flet.components.router._match_routes`, internal,
used here only as evidence) against the reproducer's `ROUTES`, and checks the
pure helpers in `src/routes.py`. Exits non-zero on the first failure.
"""

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent / "src"))

from flet.components.router import _match_routes, _split_chain_into_view_levels
from routes import drill_href, parent_of, stack_depth

from main import ROUTES

Q = quote("break--2026-05-13T12:30:00-07:00", safe="")
LEVELS = {
    # location: the (kind, ident) each drill level sees, in order
    "/now/session/42/speaker/17/session/99/room/room-102a": [
        ("session", "42"),
        ("speaker", "17"),
        ("session", "99"),
        ("room", "room-102a"),
    ],
    f"/schedule/session/{Q}/speaker/%C3%A7~31": [
        ("session", Q),
        ("speaker", "%C3%A7~31"),
    ],
    "/now/session/poster%20detail%2B1/speaker/%C3%A7~31/session/7": [
        ("session", "poster%20detail%2B1"),
        ("speaker", "%C3%A7~31"),
        ("session", "7"),
    ],
    "/more/speakers/speaker/17/session/42": [("speaker", "17"), ("session", "42")],
    "/search/speaker/17/session/42": [("speaker", "17"), ("session", "42")],
}
BACK = {
    # (location, search base): where Back goes
    ("/now/session/42/speaker/17", "/now"): "/now/session/42",
    ("/now/session/42", "/now"): "/now",
    ("/more/speakers/speaker/17", "/now"): "/more/speakers",
    ("/more/speakers", "/now"): "/more",
    ("/schedule", "/now"): "/",
    ("/search/speaker/17/session/42", "/map"): "/search/speaker/17",
    ("/search/speaker/17", "/map"): "/search",
    (
        "/search?scope=rooms",
        "/map/room/hall-a?highlight=42",
    ): "/map/room/hall-a?highlight=42",
}
DEPTH = {
    ("/now", "/now"): 1,
    ("/now/session/42/speaker/17/session/99/room/room-102a", "/now"): 5,
    ("/more/speakers/speaker/17", "/now"): 3,
    ("/search", "/schedule/session/d1-03"): 3,
    ("/search/speaker/17/session/42", "/schedule/session/d1-03"): 5,
}


def drill_levels(location: str) -> list[tuple[str, str]]:
    """The (kind, ident) params each View level of location sees, drill levels only."""
    chain = _match_routes(ROUTES, location)
    assert chain is not None, f"no match for {location}"
    _, entries = _split_chain_into_view_levels(chain)
    levels = []
    for match, _ in entries:
        params: dict[str, str] = {}
        for m in chain:  # the Router accumulates params up to each level
            params.update(m.params)
            if m is match:
                break
        if "kind" in match.params:
            levels.append((params["kind"], params["ident"]))
    return levels


def main() -> None:
    """Run every check and print one line per check."""
    for location, want in LEVELS.items():
        got = drill_levels(location)
        assert got == want, (location, got, want)
        print(f"levels ok  {location}")
    for (location, base), want in BACK.items():
        got = parent_of(location, base)
        assert got == want, (location, got, want)
        print(f"back ok    {location} -> {got}")
    for (location, base), want in DEPTH.items():
        assert stack_depth(location, base) == want, (location, want)
        print(f"depth ok   {location} = {want}")
    assert (
        drill_href("/now", "session", "poster detail+1")
        == "/now/session/poster%20detail%2B1"
    )
    assert _match_routes(ROUTES, "/now/bogus/1") is None
    assert _match_routes(ROUTES, "/now/session") is None
    print("all checks passed")


if __name__ == "__main__":
    main()
