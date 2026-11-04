"""About PyCon US (`/more/about`): who, when and where, in the conference's own words.

From the top (INFO-02, INFO-05, D-28):

- the band, the third brand moment: a compact indigo card with the year's name, its
  dates and its city, all from `conference.toml` (D-35), where Ionic hard-coded dates
  that disagreed with its own reminders. In high contrast it takes the HC roles, as
  Now's header does (D-306);
- the feed's `about` block, converted to Markdown once per feed version (D-130) and
  rendered as every feed text is (D-116);
- "Plan your visit": Help & safety and Venue & hours, pushed under this page so Back
  returns here (D-207's pattern), and the website, which opens in the browser.

Everything is on the device (bundled year data, the cached or bundled feed), so the page
shows at once and offline, with no loader (INFO-05).
"""

from urllib.parse import urlsplit

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.timefmt import date_range_label
from pycon_us.prefs import use_prefs
from pycon_us.screens.now_header import spoken
from pycon_us.services import use_services
from pycon_us.ui.info_page import GUTTER, FeedBlock
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.widths import READING, sides, use_margin

SCREEN = "about"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "About PyCon US"
"""The page's name: its app bar's title and its More row."""

LOCATION = "/more/about"
"""The page's own location; the pages it links to are pushed under it."""

PLAN = "Plan your visit"
"""The heading over the page's links."""

NO_ABOUT = "PyCon US's own description isn't on this device yet."
"""What stands for the feed's block before a feed with one is on the device."""


@ft.component
def AboutPycon() -> ft.View:
    """The About PyCon US page: the band, the feed's about text, then the links."""
    svc = use_services()
    prefs = use_prefs()
    margin = use_margin(READING)  # the info pages' width class (D-305)
    info = svc.year.conference
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=ft.ListView(
            [
                Band(info, dark=prefs.dark),
                FeedBlock("about", screen=SCREEN, empty=no_about()),
                SectionHeader(PLAN),
                # Pushed under this page, so Back returns here (D-207's pattern);
                # titled and led as More lists the same pages.
                LinkTile(
                    "Help & safety",
                    f"{LOCATION}/help",
                    icon=ft.Icons.SUPPORT_OUTLINED,
                    identifier=f"{SCREEN}.help",
                ),
                LinkTile(
                    "Venue & hours",
                    f"{LOCATION}/venue",
                    icon=ft.Icons.PLACE_OUTLINED,
                    identifier=f"{SCREEN}.venue",
                ),
                website_row(info),
            ],
            expand=True,
            padding=sides(margin, top=8, bottom=GUTTER),
        ),
    )


def band_lines(info: ConferenceInfo) -> tuple[str, str]:
    """Return the band's two lines: the name, then "May 13–19 · Long Beach, CA".

    Args:
        info: The year's facts, from `conference.toml`.
    """
    return info.name, f"{date_range_label(info.first_day, info.last_day)} · {info.city}"


def band_phrase(info: ConferenceInfo) -> str:
    """Return what a screen reader says for the band: one phrase (D-33).

    "PyCon US 2026. May 13 to 19, Long Beach, CA." (`spoken()`, as Now's header).

    Args:
        info: The year's facts.
    """
    return " ".join(f"{spoken(line)}." for line in band_lines(info))


def band_colors(*, dark: bool) -> tuple[ft.Colors, ft.Colors]:
    """Return the band's fill and ink roles: the brand indigo in both schemes.

    Light `primary` with `on_primary`; dark `primary_container` with
    `on_primary_container`, since the dark `primary` is a pale indigo. In high
    contrast both containers equal `primary`, so the same roles give HC's
    `primary` / `on_primary` (D-306), as Now's header takes them.

    Args:
        dark: The dark scheme is on screen.
    """
    if dark:
        return ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER
    return ft.Colors.PRIMARY, ft.Colors.ON_PRIMARY


def Band(info: ConferenceInfo, *, dark: bool) -> ft.Control:
    """Return the band: the year's name, dates and city on the brand indigo (D-28).

    Compact beside Now's header: no icon, two lines, 16 dp of padding. One heading
    node, the first under the bar's title (level 2, D-211), read as `band_phrase()`.
    Its fill sets it apart from the page in every scheme, HC's included, so it needs no
    line there (D-306).

    Args:
        info: The year's facts.
        dark: The dark scheme is on screen (`Prefs.dark`); in high contrast the
            roles resolve against the HC scheme on their own.
    """
    fill, ink = band_colors(dark=dark)
    name, line = band_lines(info)
    return ft.Semantics(
        label=band_phrase(info),
        header=True,
        heading_level=2,  # under the bar's "About PyCon US" (D-211)
        identifier=f"{SCREEN}.band",
        container=True,
        exclude_semantics=True,  # the phrase replaces the lines
        content=ft.Container(
            ft.Column(
                [
                    ft.Text(name, theme_style=ft.TextThemeStyle.TITLE_LARGE, color=ink),
                    ft.Text(line, theme_style=ft.TextThemeStyle.BODY_LARGE, color=ink),
                ],
                spacing=4,
            ),
            bgcolor=fill,
            border_radius=16,  # the Now header's shape (ux.md §3.6)
            padding=16,
            margin=ft.Margin.only(left=GUTTER, top=8, right=GUTTER, bottom=8),
        ),
    )


def no_about() -> ft.Control:
    """Return the line that stands for the feed's block before it is on the device."""
    return ft.Container(
        ft.Text(
            NO_ABOUT,
            theme_style=ft.TextThemeStyle.BODY_LARGE,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        padding=ft.Padding.symmetric(horizontal=GUTTER, vertical=8),
    )


def website_row(info: ConferenceInfo) -> ft.Control:
    """Return the website's row: an external link read "…, Opens in browser".

    Args:
        info: The year's facts, for its `site_url`.
    """
    return LinkTile(
        f"{info.name} website",
        info.site_url,
        icon=ft.Icons.PUBLIC,
        subtitle=urlsplit(info.site_url).hostname or info.site_url,
        identifier=f"{SCREEN}.website",
    )
