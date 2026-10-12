"""Pure route helpers for the S4 reproducer: tab roots, drill links and Back targets.

They import nothing from Flet, so ``check_routes.py`` tests them on the host. The
shapes follow decisions §M and architecture §5.3: five tab roots, More pages, the
global modal ``/search`` and a recursive drill of ``<kind>/<id>`` pairs.
"""

from urllib.parse import quote, urlparse

DRILL_KINDS = ("session", "speaker", "room")
TABS = ("/now", "/schedule", "/my-schedule", "/map", "/more")
PAGE_PATHS = frozenset({*TABS, "/more/speakers", "/search"})


def drill_href(view_path: str, kind: str, ident: str) -> str:
    """The location that pushes one detail level on top of the View at view_path."""
    return f"{view_path.rstrip('/')}/{kind}/{quote(ident, safe='')}"


def tab_of(path: str) -> int | None:
    """The index of the tab whose stack holds path, or None (search, the start)."""
    path = urlparse(path).path
    for index, root in enumerate(TABS):
        if path == root or path.startswith(root + "/"):
            return index
    return None


def parent_of(route: str, search_base: str = "/now") -> str:
    """Where Back goes from route (D-19).

    Drop the last drill pair, else walk up to the nearest page. ``/search``
    itself returns to search_base, the location (query included) it was opened
    from. A tab root returns ``/``, which the start route sends to Now.
    """
    parts = urlparse(route).path.strip("/").split("/")
    if parts == ["search"]:
        return search_base
    if len(parts) >= 3 and parts[-2] in DRILL_KINDS:
        return "/" + "/".join(parts[:-2])
    parent = parts[:-1]
    while parent and "/" + "/".join(parent) not in PAGE_PATHS:
        parent.pop()
    return "/" + "/".join(parent)


def stack_depth(route: str, search_base: str = "/now") -> int:
    """How many Views the Router should stack for route.

    One per page level plus one per drill pair; search sits on top of its base.
    """
    parts = [p for p in urlparse(route).path.split("/") if p]
    if not parts:
        return 1
    if parts[0] == "search":
        return stack_depth(search_base) + 1 + (len(parts) - 1) // 2
    depth = 0
    while parts:
        if len(parts) >= 2 and parts[-2] in DRILL_KINDS:
            parts = parts[:-2]
        else:
            parts = parts[:-1]
        depth += 1
    return depth
