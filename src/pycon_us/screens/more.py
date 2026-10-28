"""More (``/more``): one flat, sectioned list instead of Ionic's drawer (D-15, ux.md §2.2).

A section shows once its pages exist, so no row is dead. In P0 that is **Programme**,
whose pages are stubs until P1, and **You**: Settings (P2, THEME-01), which took over
the Appearance rows that stood in for it here (D-169, D-286), then About this app and
Developer, which is always there when not embedded and, in a packaged build, once
unlocked in About this app (D-73, D-187). **Expo & sponsors** came with the Sponsors
page (#395), Job listings with theirs (#399) and Expo hall, in a year with booths, with
``?booth=`` (#405), **At the venue** with Wi-Fi (D-280) and
Help & safety (D-281), Venue & hours first (D-313), and **About** with About PyCon US (#414), About the PSF (D-283) and Social media
(D-284); their other rows join with their P2 pages. The profile row comes first while
a mock API URL is set (D-51, SHELL-12): "Sign in" signed out, else the account's
avatar, nickname and email, not tappable until the Account page (#688) exists, so it
is never dead; it appears, disappears and changes live with ``Prefs`` and the
``Account`` store. Staff tools join under it with P3's tools (D-16).
Every row pushes its page, so Back returns here (D-17): Expo hall is the drill's
``/more/plan/expo``, a pushed View like any page.
"""

from typing import NamedTuple

import flet as ft

from pycon_us.account import Account, use_account
from pycon_us.core.speakers import initials
from pycon_us.locations import drill_href
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.rows import AVATAR_RADIUS, LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button
from pycon_us.ui.semantics import named
from pycon_us.ui.widths import LIST, sides, use_margin
from pycon_us.year_map import EXPO_PLAN


class MoreEntry(NamedTuple):
    """A row of the More list: a page under ``/more`` (ux.md §2.2)."""

    title: str
    location: str
    icon: ft.IconData
    name: str = ""
    """The page's name in the identifier, for a location that isn't a page's own."""

    @property
    def identifier(self) -> str:
        """The semantics identifier UI tests find it by: ``more.<page>`` (section M)."""
        page = self.name or self.location.removeprefix("/more/")
        return "more." + page.replace("-", "_")


PROGRAMME = (
    MoreEntry("Speakers", "/more/speakers", ft.Icons.PEOPLE_OUTLINE),
    MoreEntry("Tracks & session types", "/more/tracks", ft.Icons.SELL_OUTLINED),
    MoreEntry("Keynotes", "/more/keynotes", ft.Icons.CO_PRESENT_OUTLINED),
    MoreEntry("Open spaces", "/more/open-spaces", ft.Icons.FORUM_OUTLINED),
    MoreEntry("Lightning talks", "/more/lightning-talks", ft.Icons.BOLT_OUTLINED),
    MoreEntry("Sprints", "/more/sprints", ft.Icons.ROCKET_LAUNCH_OUTLINED),
)
"""The Programme section, in the list's order (ux.md §2.2; icons §3.7)."""

EXPO_HALL = MoreEntry(
    "Expo hall", drill_href("/more", "plan", EXPO_PLAN), ft.Icons.MAP_OUTLINED, "expo"
)
"""The expo hall pushed on More (``ExpoPlan``), only in a year with booths."""

EXPO_AND_SPONSORS = (
    MoreEntry("Sponsors", "/more/sponsors", ft.Icons.STOREFRONT_OUTLINED),
    EXPO_HALL,
    MoreEntry("Job listings", "/more/jobs", ft.Icons.WORK_OUTLINE),
)
"""The Expo & sponsors section, in the list's order (ux.md §2.2)."""

AT_THE_VENUE = (
    MoreEntry("Venue & hours", "/more/venue", ft.Icons.PLACE_OUTLINED),
    MoreEntry("Wi-Fi", "/more/wifi", ft.Icons.WIFI),
    MoreEntry("Help & safety", "/more/help", ft.Icons.SUPPORT_OUTLINED),
)
"""The At the venue section, in the list's order (ux.md §2.2; icons §3.7)."""

ABOUT = (
    MoreEntry("About PyCon US", "/more/about", ft.Icons.INFO_OUTLINE),
    MoreEntry("About the PSF", "/more/psf", ft.Icons.VOLUNTEER_ACTIVISM_OUTLINED),
    MoreEntry("Social media", "/more/social", ft.Icons.LANGUAGE),
)
"""The About section, in the list's order (ux.md §2.2; icons §3.7)."""

SETTINGS = MoreEntry("Settings", "/more/settings", ft.Icons.SETTINGS_OUTLINED)
ABOUT_APP = MoreEntry("About this app", "/more/app", ft.Icons.INFO_OUTLINE)
SIGN_IN = MoreEntry("Sign in", "/more/sign-in", ft.Icons.ACCOUNT_CIRCLE_OUTLINED)
"""The profile row signed out, only while a mock API URL is set (D-51)."""

DEVELOPER = MoreEntry(
    "Developer options", "/more/developer", ft.Icons.DEVELOPER_MODE_OUTLINED
)

MORE_PAGES = (
    *PROGRAMME,
    *EXPO_AND_SPONSORS,
    *AT_THE_VENUE,
    *ABOUT,
    SETTINGS,
    ABOUT_APP,
    DEVELOPER,
)
"""Every page the list links to; later phases add theirs with their sections."""


@ft.component
def More() -> ft.View:
    """The More root: its sections, the search, and a re-tap that scrolls to the top."""
    list_ref, scroll_to_top = use_scroll_to_top()
    margin = use_margin(LIST)  # its width class (D-305)
    svc = use_services()
    prefs = use_prefs()
    account = use_account()
    you = [SETTINGS, ABOUT_APP]
    if prefs.developer:
        you.append(DEVELOPER)
    booths = bool(svc.year.map.booths)  # no hall, no row: none is dead
    expo = [entry for entry in EXPO_AND_SPONSORS if booths or entry != EXPO_HALL]
    return AppScaffold(
        title="More",
        actions=[search_button(svc.memory, "all")],
        body=ft.ListView(
            [
                *([profile_row(account)] if prefs.private_api_enabled else []),
                SectionHeader("Programme"),
                *(link(entry) for entry in PROGRAMME),
                SectionHeader("Expo & sponsors"),
                *(link(entry) for entry in expo),
                SectionHeader("At the venue"),
                *(link(entry) for entry in AT_THE_VENUE),
                SectionHeader("About"),
                *(link(entry) for entry in ABOUT),
                SectionHeader("You"),
                *(link(entry) for entry in you),
            ],
            expand=True,
            ref=list_ref,
            padding=sides(margin),
        ),
        on_retap=scroll_to_top,
    )


def link(entry: MoreEntry) -> ft.Control:
    """Return the row of one More page.

    Args:
        entry: The page.
    """
    return LinkTile(
        entry.title, entry.location, icon=entry.icon, identifier=entry.identifier
    )


def profile_row(account: Account) -> ft.Control:
    """Return More's first row: "Sign in", or who is signed in (ux.md §2.2, SHELL-12).

    Signed in, one node read as the nickname and the email, with the identifier
    ``more.account``; not a button until the Account page exists (#688), so it is
    never a dead one (SHELL-09). The avatar's letters stay out of it, as a speaker
    row's do.

    Args:
        account: The session's ``Account`` store.
    """
    if not account.signed_in:
        return link(SIGN_IN)
    return named(
        "more.account",
        ft.ListTile(
            # Excluded: the name says who it is; the letters would be read first.
            leading=ft.Semantics(
                exclude_semantics=True,
                content=ft.CircleAvatar(
                    content=ft.Text(account_initials(account.nickname, account.email)),
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    color=ft.Colors.ON_PRIMARY_CONTAINER,
                    radius=AVATAR_RADIUS,
                ),
            ),
            title=ft.Text(account.nickname or account.email),
            subtitle=ft.Text(account.email) if account.nickname else None,
        ),
    )


def account_initials(nickname: str, email: str) -> str:
    """Return an account avatar's letters: the nickname's initials, else the email's first.

    Args:
        nickname: The account's nickname, maybe empty or without a letter.
        email: The account's email, never empty while signed in.
    """
    return initials(nickname) or email[:1].upper()
