"""The rows lists are made of (decisions §M): so far ``LinkTile``, a row that opens a link.

P1 adds the session, notice and speaker rows, the time gutter and ``LocationCard`` here
(ux.md §3.9).

``LinkTile`` follows the link rule (INFO-14, ux.md §4.7), in one place: ``link_kind()``
says what a target is, and ``open_link()`` opens it the way that kind opens, for rows
and for Markdown's ``on_tap_link`` alike.

- An in-app page (a location such as ``/more/speakers``) is pushed; its row ends in
  ``CHEVRON_RIGHT``.
- A web page opens in the in-app browser view (``LaunchMode.IN_APP_BROWSER_VIEW``), so
  the attendee stays in context; its row ends in ``OPEN_IN_NEW``.
- A social profile or a map opens in the app that handles it
  (``LaunchMode.EXTERNAL_APPLICATION``): the caller says so for a web address
  (``app=True``), and a ``geo:`` link always does; its row ends in ``OPEN_IN_NEW`` too.
- ``tel:`` and ``mailto:`` hand off to the phone or mail app, and their row has a Copy
  button beside it: a simulator, an iPad or a phone without a mail account has nothing
  to hand off to, and without U6 the app cannot ask first.
"""

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any
from urllib.parse import unquote, urlsplit

import flet as ft

from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)


class LinkKind(Enum):
    """What a link's target is, which decides how it opens (ux.md §4.7)."""

    PAGE = "page"
    """A page of the app: pushed."""
    WEB = "web"
    """A web page: the in-app browser view."""
    APP = "app"
    """A social profile or a map: the app that handles it."""
    PHONE = "phone"
    """A ``tel:`` link: the phone app, with Copy."""
    EMAIL = "email"
    """A ``mailto:`` link: the mail app, with Copy."""


LAUNCH_MODES: dict[LinkKind, ft.LaunchMode] = {
    LinkKind.WEB: ft.LaunchMode.IN_APP_BROWSER_VIEW,
    LinkKind.APP: ft.LaunchMode.EXTERNAL_APPLICATION,
    LinkKind.PHONE: ft.LaunchMode.EXTERNAL_APPLICATION,
    LinkKind.EMAIL: ft.LaunchMode.EXTERNAL_APPLICATION,
}
"""How ``UrlLauncher.launch_url`` opens each kind of external link."""

OPENS_IN: dict[LinkKind, str] = {
    LinkKind.WEB: "Opens in browser",
    LinkKind.APP: "Opens in another app",
}
"""What a screen reader hears after a row that leaves the app: the ``OPEN_IN_NEW``
icon's label, which visually says the same (D-33). Phone and email rows say it in
their title ("Call the Code of Conduct hotline")."""

COPY_TOOLTIPS = {
    LinkKind.PHONE: "Copy phone number",
    LinkKind.EMAIL: "Copy email address",
}
COPIED = {LinkKind.PHONE: "Phone number copied", LinkKind.EMAIL: "Email address copied"}

_WEB_SCHEMES = ("http", "https")


def link_kind(target: str, *, app: bool = False) -> LinkKind:
    """Return what ``target`` is, by the link rule (INFO-14).

    Args:
        target: An app location (``/more/speakers``) or a URL: ``http(s)``, ``geo``,
            ``tel`` or ``mailto``.
        app: The web address is a social profile or a map, which opens in the app
            that handles it rather than in the in-app browser.

    Returns:
        The kind; ``LAUNCH_MODES`` says how an external one opens.

    Raises:
        ValueError: ``target`` is none of those, or a page is marked ``app``.
    """
    if target.startswith("/"):
        if app:
            raise ValueError(f"an app page opens no other app: {target!r}")
        return LinkKind.PAGE
    scheme = urlsplit(target).scheme.lower()
    if scheme in _WEB_SCHEMES:
        return LinkKind.APP if app else LinkKind.WEB
    if scheme == "geo":
        return LinkKind.APP
    if scheme == "tel":
        return LinkKind.PHONE
    if scheme == "mailto":
        return LinkKind.EMAIL
    raise ValueError(f"not a link the app opens: {target!r}")


def contact_of(target: str) -> str:
    """Return what Copy copies for a ``tel:`` or ``mailto:`` link.

    Args:
        target: The link, e.g. ``tel:+1-562-662-4082`` or ``mailto:a@b.org?subject=x``.

    Returns:
        The number or the address, without the scheme or a query:
        ``+1-562-662-4082``, ``a@b.org``.
    """
    return unquote(urlsplit(target).path)


async def open_link(svc: Services, target: str, *, app: bool = False) -> None:
    """Open ``target`` by the link rule; call it from an event handler.

    A page is pushed. Anything else goes to ``UrlLauncher.launch_url`` with its kind's
    mode; when the platform reports that it could not open it, a SnackBar says
    "Couldn't open the link" (an expected failure, D-71). A phone or a simulator with
    no app for a ``tel:`` link may also do nothing without saying so, which is why
    those rows offer Copy.

    Args:
        svc: The session's services, for the launcher.
        target: An app location or a URL (``link_kind()``).
        app: The web address opens in the app that handles it (``link_kind()``).
    """
    page = ft.context.page
    kind = link_kind(target, app=app)
    if kind is LinkKind.PAGE:
        page.navigate(target)
        return
    try:
        await svc.launcher.launch_url(target, mode=LAUNCH_MODES[kind])
    except SERVICE_ERRORS:
        # The kind only: a mailto: target holds an address, which never goes in the log.
        logger.warning("Could not open the %s link", kind.value, exc_info=True)
        _say("Couldn't open the link")


async def copy_contact(svc: Services, target: str) -> None:
    """Copy a ``tel:`` or ``mailto:`` link's number or address, and say so.

    Args:
        svc: The session's services, for the clipboard.
        target: The link (``contact_of()``).

    Raises:
        ValueError: ``target`` is not a ``tel:`` or ``mailto:`` link.
    """
    kind = link_kind(target)
    if kind not in COPIED:
        raise ValueError(f"only phone and email links copy: {target!r}")
    try:
        await svc.clipboard.set(contact_of(target))
    except SERVICE_ERRORS:
        logger.warning("Could not copy the %s link", kind.value, exc_info=True)
        _say("Couldn't copy")
        return
    _say(COPIED[kind])


def _say(text: str) -> None:
    ft.context.page.show_dialog(
        ft.SnackBar(ft.Text(text), behavior=ft.SnackBarBehavior.FLOATING)
    )


def LinkTile(
    title: str,
    target: str,
    *,
    icon: ft.IconData | None = None,
    subtitle: str | None = None,
    identifier: str | None = None,
    app: bool = False,
) -> ft.Control:
    """Return a row that opens ``target`` by the link rule: a page or a link.

    A Material ``ListTile``, so it is at least 56 dp tall (72 with a subtitle), more
    than the 48 dp target (D-33), and grows with the text. It is one node for screen
    readers, read as its title and subtitle: a button for a page; a link for anything
    else, whose ``OPEN_IN_NEW`` icon is read as "Opens in browser" (or "Opens in
    another app"). A phone or email row has a Copy button beside it, a stop of its
    own, as a session row's star is (ux.md §3.9).

    An in-app row is built here. An external one needs the session's services when it
    is tapped, so it is a component, which reads them (``use_services()``).

    Args:
        title: The row's text, in sentence case; a phone or email row says what a tap
            does ("Call the Code of Conduct hotline").
        target: Where a tap goes: a page (``/more/speakers``), for a detail
            ``drill_href(view_path, ...)`` so Back returns to this row's View, or a URL
            (``link_kind()``).
        icon: A leading icon, outlined (D-27); none for rows of names.
        subtitle: A second line, if any: for a phone or email row, the number or the
            address.
        identifier: The row's semantics identifier for UI tests, e.g.
            ``more.speakers`` (decisions §M); a Copy button gets ``<identifier>.copy``.
        app: A web address opens in the app that handles it: a social profile, a map.

    Raises:
        ValueError: ``target`` is not a link the app opens (``link_kind()``).
    """
    kind = link_kind(target, app=app)
    if kind is not LinkKind.PAGE:
        return _ExternalLinkTile(
            title, target, kind, icon=icon, subtitle=subtitle, identifier=identifier
        )
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(target)

    tile = _tile(title, icon, subtitle, ft.Icon(ft.Icons.CHEVRON_RIGHT), go)
    # An identifier without a label of its own joins the merged node (D-166).
    if identifier is not None:
        tile = ft.Semantics(identifier=identifier, content=tile)
    return ft.MergeSemantics(content=tile)


@ft.component
def _ExternalLinkTile(
    title: str,
    target: str,
    kind: LinkKind,
    *,
    icon: ft.IconData | None,
    subtitle: str | None,
    identifier: str | None,
) -> ft.Control:
    """The external form of ``LinkTile``: a link that leaves the app, maybe with Copy."""
    svc = use_services()

    @report_errors
    async def launch() -> None:
        await open_link(svc, target, app=kind is LinkKind.APP)

    @report_errors
    async def copy() -> None:
        await copy_contact(svc, target)

    opens_in = OPENS_IN.get(kind)
    trailing = None
    if opens_in is not None:
        trailing = ft.Icon(ft.Icons.OPEN_IN_NEW, semantics_label=opens_in)
    row = ft.MergeSemantics(
        content=ft.Semantics(
            identifier=identifier,
            link=True,
            content=_tile(title, icon, subtitle, trailing, launch),
        )
    )
    tooltip = COPY_TOOLTIPS.get(kind)
    if tooltip is None:
        return row
    copy_button: ft.Control = ft.IconButton(
        ft.Icons.CONTENT_COPY_OUTLINED, tooltip=tooltip, on_click=copy
    )
    if identifier is not None:
        copy_button = ft.Semantics(identifier=f"{identifier}.copy", content=copy_button)
    return ft.Row(
        [
            ft.Container(row, expand=True),
            ft.Container(copy_button, padding=ft.Padding.only(right=8)),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _tile(
    title: str,
    icon: ft.IconData | None,
    subtitle: str | None,
    trailing: ft.Control | None,
    on_click: Callable[[], Any],
) -> ft.ListTile:
    return ft.ListTile(
        leading=ft.Icon(icon) if icon is not None else None,
        title=title,
        subtitle=subtitle,
        trailing=trailing,
        on_click=on_click,
    )
