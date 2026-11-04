"""Social media (`/more/social`): the hashtags to copy, and where to follow PyCon US.

The year's `[social]` table (`content.toml`, D-284) gives both, so the page shows at
once, offline (INFO-05, INFO-10). Each hashtag is a chip that copies it through
`copy_text()`, with one confirmation (D-263), where Ionic's chips looked tappable and
did nothing. Then the profiles, under PyCon US and the PSF, and the blogs: link rows
with the brand's mark and the handle under the name. A profile opens in its app, a blog
in the in-app browser (the link rule, ux.md §4.7). A year without the table shows the
feed's own `social-media` block, and without that an empty state that points to the
website (`InfoBody`).
"""

from urllib.parse import urlsplit

import flet as ft

from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.brands import brand_icon
from pycon_us.ui.info_page import GUTTER, InfoBody
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.links import copy_text
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.year_links import SOCIAL_SECTIONS, SocialInfo, SocialLink

SCREEN = "social"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "Social media"
"""The page's name: its app bar's title and its More row (ux.md §2.2)."""

HASHTAGS = "Hashtags"
HASHTAGS_HINT = "Tap one to copy it, then paste it into your post."
HASHTAG_COPIED = "Hashtag copied"
HASHTAG_NOT_COPIED = "Couldn't copy the hashtag"

BLOGS = "blogs"
"""The section of web pages: every other section's links are profiles, which open in
their app (`app=True`), where a blog opens in the in-app browser (ux.md §4.7)."""

NO_BRAND_ICON = ft.Icons.RSS_FEED_OUTLINED
"""A link without a brand mark (a blog on its own site) leads with a feed."""

NO_SOCIAL = "No social links yet"


def copy_label(hashtag: str) -> str:
    """Return what a screen reader says for a hashtag's chip: "Copy hashtag #PyConUS".

    Args:
        hashtag: The hashtag, with its `#`.
    """
    return f"Copy hashtag {hashtag}"


@ft.component
def Social() -> ft.View:
    """The Social media page: the year's hashtags and links, else the feed's block."""
    svc = use_services()
    social = svc.year.content.social
    blocks = [] if social is None else social_blocks(svc, social)
    site = urlsplit(svc.year.conference.site_url).hostname or ""
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=InfoBody(
            blocks, block="social-media", screen=SCREEN, empty=empty_state(site)
        ),
    )


def empty_state(site: str) -> ft.Control:
    """Return the page's empty state, which sends the attendee to the website.

    No button: the website names its own profiles, and the hashtags need the year's
    data (ux.md §4.6's way out in a sentence).

    Args:
        site: The year's site's host, `us.pycon.org`.
    """
    return EmptyState(
        NO_SOCIAL,
        icon=ft.Icons.LANGUAGE,
        body=f"The website, {site}, links to PyCon US's profiles.",
        identifier=f"{SCREEN}.empty",
    )


def social_blocks(svc: Services, social: SocialInfo) -> list[ft.Control]:
    """Return the page's blocks: the hashtags, then each section's links.

    A section without links is left out, heading and all.

    Args:
        svc: The session's services, for the clipboard.
        social: The year's hashtags and links.
    """
    blocks: list[ft.Control] = []
    if social.hashtags:
        blocks += [SectionHeader(HASHTAGS), hashtag_chips(svc, social.hashtags)]
    for section, heading in SOCIAL_SECTIONS.items():
        links = [link for link in social.links if link.section == section]
        if links:
            blocks += [SectionHeader(heading), *(link_row(link) for link in links)]
    return blocks


def hashtag_chips(svc: Services, hashtags: tuple[str, ...]) -> ft.Control:
    """Return the hashtags as chips that copy, under a line that says so.

    The chips wrap onto more lines rather than scroll: there are few, and at the
    largest text every one stays in sight.

    Args:
        svc: The session's services, for the clipboard.
        hashtags: The hashtags, with their `#`.
    """
    return ft.Container(
        ft.Column(
            [
                ft.Text(
                    HASHTAGS_HINT,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(
                    [
                        hashtag_chip(svc, index, hashtag)
                        for index, hashtag in enumerate(hashtags)
                    ],
                    wrap=True,
                    spacing=8,
                    run_spacing=8,
                ),
            ],
            spacing=8,
        ),
        padding=ft.Padding.symmetric(horizontal=GUTTER, vertical=8),
    )


def hashtag_chip(svc: Services, index: int, hashtag: str) -> ft.Control:
    """Return one hashtag's chip: a tap copies it, and says so once.

    One node for screen readers, a button named "Copy hashtag #PyConUS", with the
    identifier `social.hashtag.<index>`. Its copy icon is decorative: the name
    says what a tap does. Flutter's chip keeps a 48 dp target around its 32 dp shape
    (`MaterialTapTargetSize.padded`, D-33).

    Args:
        svc: The session's services, for the clipboard.
        index: The hashtag's place on the page, from 0, for its identifier.
        hashtag: The hashtag, with its `#`, exactly as it is copied.
    """

    @report_errors
    async def copy() -> None:
        await copy_text(svc, hashtag, HASHTAG_COPIED, HASHTAG_NOT_COPIED)

    return named(
        f"{SCREEN}.hashtag.{index}",
        ft.Chip(
            label=chip_label(hashtag),
            # The label draws the icon and the side padding (chip_label(), F69).
            padding=ft.Padding.symmetric(vertical=8),
            label_padding=ft.Padding.all(0),
            on_click=copy,
        ),
    )


def chip_label(hashtag: str) -> ft.Container:
    """Return a hashtag chip's label: the copy icon, then the hashtag, which may wrap.

    As the Schedule's filter chips do (D-249): Flutter's chip shows its label on one
    line and fades the rest, and cuts a wrapped one it measured at its whole width
    beside a leading icon (F69), so at the largest text "#PyConUS2026" lost its end.
    The label holds the icon and the side padding instead, and is laid out at the
    same width both times.

    Args:
        hashtag: The hashtag, with its `#`.
    """
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.CONTENT_COPY_OUTLINED,
                    size=18,  # M3's chip icon, growing with the text as Flutter's
                    color=ft.Colors.PRIMARY,  # M3's assist chip icon
                    apply_text_scaling=True,
                ),
                ft.Text(
                    hashtag,
                    semantics_label=copy_label(hashtag),
                    # One word: at the largest text on the narrowest phone it may
                    # break inside, never fade.
                    max_lines=3,
                    expand=True,
                    expand_loose=True,
                ),
            ],
            spacing=8,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        # M3's 8 dp chip padding plus its 8 dp label padding; the icon takes the
        # label padding's place at the start.
        padding=ft.Padding.only(left=8, right=16),
        # Painted, so a tap anywhere on the label lands: the chip hit-tests only
        # its label's centre (F69).
        bgcolor=ft.Colors.TRANSPARENT,
    )


def link_row(link: SocialLink) -> ft.Control:
    """Return a profile's or a blog's row: its mark, its name, its handle under it.

    Read as one link, "Mastodon, @pycon@fosstodon.org, Opens in another app" (a blog:
    "Opens in browser"); the mark is decorative (D-264).

    Args:
        link: The profile or the blog.
    """
    return LinkTile(
        link.label,
        link.url,
        icon=brand_icon(link.brand) if link.brand else NO_BRAND_ICON,
        subtitle=link.handle,
        identifier=f"{SCREEN}.link.{link.key}",
        app=link.section != BLOGS,
    )
