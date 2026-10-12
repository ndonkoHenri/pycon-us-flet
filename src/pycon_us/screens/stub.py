"""The minimal chrome every stub screen shares, until ``AppScaffold`` and the bar land.

``stub_view()`` gives each screen a View with a plain ``AppBar`` and the Back rules the
route table needs: the Material back arrow on pushed Views (D-10), one View key for the
tab roots (D-142), Back on a non-Now root going to Now (D-17), and the top View's
location recorded for the start route (D-143). #76 replaces it with ``AppScaffold``
and #75 adds the bottom bar; until then Now links to the other roots.
"""

import flet as ft

from pycon_us.locations import TAB_ROOTS, parent_of
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import ViewMemory


def stub_view(
    *, title: str, controls: list[ft.Control], actions: list[ft.Control] | None = None
) -> ft.View:
    """Return a screen's View: its title, its route and params, then its controls.

    A plain function that calls hooks, so a screen calls it exactly once per render,
    in every branch (hooks are unconditional, D-70).

    Args:
        title: The app bar's title.
        controls: The body, in a ``ListView`` inside a ``SafeArea``.
        actions: The app bar's actions, e.g. ``search_button()``.

    Returns:
        The View for this route level.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    location = ft.use_route_location()
    params = ft.use_route_params()
    memory = use_services().memory
    is_root = view_path in TAB_ROOTS
    back_to_now = is_root and view_path != "/now"
    if view_path == location:  # the top View: where a new session returns (D-143)
        memory.last_location = page.route

    @report_errors
    def go_back() -> None:
        page.navigate(parent_of(view_path, memory.search_base))

    @report_errors
    async def leave_for_now(e: ft.Event[ft.View]) -> None:
        page.navigate("/now")
        await e.control.confirm_pop(False)  # this View stays; Now replaces the root

    shown = ", ".join(f"{key}={value}" for key, value in params.items())
    return ft.View(
        route="/" if is_root else view_path,  # roots share a key: no transition (D-142)
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(title),
            center_title=False,
            automatically_imply_leading=False,
            leading=None
            if is_root
            else ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Back", on_click=go_back),
            actions=actions or [],
        ),
        can_pop=not back_to_now,
        on_confirm_pop=leave_for_now if back_to_now else None,
        controls=[
            ft.SafeArea(
                expand=True,
                content=ft.ListView(
                    [note(f"{view_path}  {shown}".rstrip(), small=True), *controls],
                    expand=True,
                ),
            )
        ],
    )


def note(text: str, *, small: bool = False) -> ft.Control:
    """Return a line of body text with the list's side padding.

    Args:
        text: The text; selectable, so a route can be copied.
        small: Use the small body style, for route details.
    """
    style = ft.TextThemeStyle.BODY_SMALL if small else ft.TextThemeStyle.BODY_MEDIUM
    return ft.Container(
        ft.Text(text, theme_style=style, selectable=True),
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
    )


def nav_tile(title: str, location: str, *, subtitle: str | None = None) -> ft.ListTile:
    """Return a row that navigates to a location: a drill link, a page or a root.

    Args:
        title: The row's text.
        location: Where a tap goes; for a detail, ``drill_href(view_path, ...)``.
        subtitle: A second line, if any.
    """
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(location)

    return ft.ListTile(
        title=title,
        subtitle=subtitle,
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        on_click=go,
    )


def search_button(memory: ViewMemory, scope: str) -> ft.IconButton:
    """Return the app bar action that opens the global search with a preset scope (D-19).

    It records the opener's location, query included, so Back from search returns
    there.

    Args:
        memory: The process's ``ViewMemory``.
        scope: ``all``, ``sessions``, ``speakers`` or ``rooms``.
    """
    page = ft.context.page

    @report_errors
    def open_search() -> None:
        memory.search_base = page.route
        page.navigate(f"/search?scope={scope}")

    return ft.IconButton(ft.Icons.SEARCH, tooltip="Search", on_click=open_search)
