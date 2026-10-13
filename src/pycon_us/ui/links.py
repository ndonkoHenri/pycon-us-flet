"""The link rule (INFO-14, ux.md §4.7): what a link's target is and how it opens.

One place for it, used by ``ui.rows.LinkTile`` and by the feed's texts
(``feed_markdown()``): ``link_kind()`` says what a target is, and ``open_link()`` opens it
the way that kind opens.

- An in-app page (a location such as ``/more/speakers``) is pushed; its row ends in
  ``CHEVRON_RIGHT``.
- A web page opens in the in-app browser view (``LaunchMode.IN_APP_BROWSER_VIEW``), so
  the attendee stays in context; its row ends in ``OPEN_IN_NEW``.
- A social profile or a map opens in the app that handles it
  (``LaunchMode.EXTERNAL_APPLICATION``): the caller says so for a web address
  (``app=True``), and a ``geo:`` link always does; its row ends in ``OPEN_IN_NEW`` too.
- ``tel:`` and ``mailto:`` hand off to the phone or mail app, and their row has a Copy
  button beside it (``copy_contact()``): a simulator, an iPad or a phone without a mail
  account has nothing to hand off to, and without U6 the app cannot ask first.

A failure says so in a SnackBar and is logged with the link's kind and the error's
class only: a ``mailto:`` target holds an address, and the platform's error text
repeats the target (D-72).

A link in a feed text (a description, a bio) is what its author wrote, so
``feed_link()`` first says which web address it stands for, if any (D-194): only
``http``, ``https`` and ``mailto`` links open, a site-relative path joins the year's
site, and a web address written without its scheme (2026's ``[pytest](pytest.org)``)
gets ``https://``.
"""

import logging
import re
from enum import Enum
from urllib.parse import unquote, urljoin, urlsplit

import flet as ft

from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.theme import MARKDOWN_STYLE

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
COPY_FAILED = {
    LinkKind.PHONE: "Couldn't copy the phone number",
    LinkKind.EMAIL: "Couldn't copy the email address",
}

SYSTEM_COPY_CONFIRMATION_SDK = 33
"""From Android 13 (API 33) the system confirms every copy itself, so the app does not
(Android's copy-and-paste guidance; ux.md §4.7)."""

COULD_NOT_OPEN = "Couldn't open the link"
"""What a SnackBar says when a link does not open (ux.md §4.7)."""

_WEB_SCHEMES = ("http", "https")
_APP_SCHEMES = (*_WEB_SCHEMES, "geo")

FEED_LINK_SCHEMES = (*_WEB_SCHEMES, "mailto")
"""The schemes a link in a feed text may have to open (D-194)."""

_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", re.IGNORECASE)
"""A host name with a dot and a top-level domain of letters: ``pytest.org``."""


def link_kind(target: str, *, app: bool = False) -> LinkKind:
    """Return what ``target`` is, by the link rule (INFO-14).

    Args:
        target: An app location (``/more/speakers``) or a URL: ``http(s)``, ``geo``,
            ``tel`` or ``mailto``.
        app: The web address is a social profile or a map, which opens in the app
            that handles it rather than in the in-app browser. Only a web address (or a
            ``geo:`` link, which always opens its app) can be marked.

    Returns:
        The kind; ``LAUNCH_MODES`` says how an external one opens.

    Raises:
        ValueError: ``target`` is none of those, or something other than a web address
            or a ``geo:`` link is marked ``app``.
    """
    scheme = "" if target.startswith("/") else urlsplit(target).scheme.lower()
    if app and scheme not in _APP_SCHEMES:
        raise ValueError(f"only a web address opens in another app: {target!r}")
    if target.startswith("/"):
        return LinkKind.PAGE
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
    except SERVICE_ERRORS as error:
        # The kind and the class only: the error's text repeats the target (D-72).
        logger.warning(
            "Could not open the %s link: %s", kind.value, type(error).__name__
        )
        _say(COULD_NOT_OPEN)


def feed_link(href: str | None, site_url: str) -> str | None:
    """Return the address a link in a feed text opens, or None when it opens nothing.

    Descriptions converted from the feed's HTML have absolute links already (D-114);
    open-space descriptions are Markdown with their links as their authors wrote them
    (D-140), so this decides what each form means (D-194):

    - ``http``, ``https`` and ``mailto`` links are themselves; any other scheme
      (``javascript:``, ``file:``, ``tel:``) opens nothing.
    - A path from the site's root (``/2026/sponsors/``), or from a host without a
      scheme (``//host/…``), joins the year's site URL, as it would on the site.
    - A web address written without its scheme, its first segment a host name
      (``pytest.org``, ``docs.pytest.org/en/stable/``), gets ``https://``, as a
      browser's address bar would: joined to the site URL it would be a page of the
      site that does not exist.
    - Anything else (``#top``, ``../slides``, ``notes``) depends on the page the text
      was written on, which the app does not know, so it opens nothing.

    Args:
        href: The link's destination, as ``Markdown``'s ``on_tap_link`` gives it.
        site_url: The year's site, ending in ``/`` (``ConferenceInfo.site_url``).

    Returns:
        A ``http``, ``https`` or ``mailto`` URL, or None.
    """
    target = (href or "").strip()
    if not target:
        return None
    if target.startswith("/"):
        return urljoin(site_url, target)
    try:
        scheme = urlsplit(target).scheme.lower()
    except ValueError:  # an address urlsplit cannot read, e.g. "http://["
        return None
    if scheme:
        return target if scheme in FEED_LINK_SCHEMES else None
    host = re.split(r"[/?#]", target, maxsplit=1)[0]
    return f"https://{target}" if _HOST.fullmatch(host) else None


async def open_feed_link(svc: Services, href: str | None) -> None:
    """Open a link tapped in a feed text, by ``feed_link()`` and the link rule.

    A link that opens nothing says so in the SnackBar a failed launch shows, rather
    than leave the tap without an answer; the log never names the link (D-72).

    Args:
        svc: The session's services: the launcher and the year's site URL.
        href: The tapped link's destination, as the feed text has it.
    """
    target = feed_link(href, svc.year.conference.site_url)
    if target is None:
        logger.warning("A link in a feed text has no address the app opens")
        _say(COULD_NOT_OPEN)
        return
    await open_link(svc, target)


def feed_markdown(
    value: str, svc: Services, *, identifier: str | None = None
) -> ft.Control:
    """Return a feed text (a description, a bio) as the app renders every one (D-116).

    Selectable Markdown with GitHub's extensions and the app's style sheet
    (``theme.MARKDOWN_STYLE``), 16 dp from the screen's edges. A tapped link opens by
    ``open_feed_link()``. Each link is a node of its own for screen readers, named by
    its text.

    Args:
        value: The Markdown, converted once per feed version (D-130).
        svc: The session's services, for the links.
        identifier: The text's semantics identifier, e.g. ``session.description``.
    """

    @report_errors
    async def tap(e: ft.Event[ft.Markdown]) -> None:
        await open_feed_link(svc, e.data)

    text = ft.Markdown(
        value,
        selectable=True,  # long text is selectable (D-26); on_tap_link still fires
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        md_style_sheet=MARKDOWN_STYLE,
        on_tap_link=tap,
    )
    return ft.Semantics(
        identifier=identifier,
        container=True,  # one node holds the text's, so the identifier has a home
        content=ft.Container(text, padding=ft.Padding.symmetric(horizontal=16)),
    )


async def copy_contact(svc: Services, target: str) -> None:
    """Copy a ``tel:`` or ``mailto:`` link's number or address, and say so.

    The confirmation is the app's SnackBar, except on Android 13 and later, whose own
    overlay already confirms every copy; a failure is said on every platform.

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
    except SERVICE_ERRORS as error:
        # The kind and the class only: the error's text repeats the address (D-72).
        logger.warning(
            "Could not copy the %s link: %s", kind.value, type(error).__name__
        )
        _say(COPY_FAILED[kind])
        return
    if not await _system_confirms_copies():
        _say(COPIED[kind])


async def _system_confirms_copies() -> bool:
    """Whether the platform shows its own confirmation of a copy: Android 13 and later."""
    page = ft.context.page
    if page.platform is not ft.PagePlatform.ANDROID:
        return False
    try:
        info = await page.get_device_info()
    except SERVICE_ERRORS:
        return False  # unsure: say it, as Android 12 and earlier need
    # Flet's device-info classes type as Any, so isinstance alone does not rule out None.
    if info is None or not isinstance(info, ft.AndroidDeviceInfo):
        return False
    return info.version.sdk >= SYSTEM_COPY_CONFIRMATION_SDK


def _say(text: str) -> None:
    ft.context.page.show_dialog(
        ft.SnackBar(ft.Text(text), behavior=ft.SnackBarBehavior.FLOATING)
    )
