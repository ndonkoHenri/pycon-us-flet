"""The body every info page hands ``AppScaffold`` (D-263, INFO-05, ux.md §6.7).

Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF and Social show
what the year's ``content.toml`` says (``year_info``), and fall back to the feed's own
block for the page (``conference.content``, converted to Markdown once per feed
version, D-130) when the year has no table for it. Either way the page renders at once
from what is on the device: bundled data, or the cached or bundled feed. There is no
skeleton and no loader, where Ionic held each page behind "Fetching latest…" for up to
10 s (INFO-05); a page with neither shows its own empty state, which names the way out.

Each block of a page sits ``GUTTER`` from the screen's sides: texts and cards in a
``GUTTER`` padding, rows (a ``ListTile``) through their own content padding, so a row's
ripple still runs edge to edge (M3 lists). The reading width (720 dp, D-09) is the
shared width class's (``ui.widths.READING``, D-305), never a cap of the page's own.
"""

from collections.abc import Sequence

import flet as ft

from pycon_us.services import use_services
from pycon_us.state import use_conference
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.widths import READING, sides, use_margin

GUTTER = 16
"""How far a page's texts and cards sit from the screen's sides, in dp (ux.md §3.6)."""


def InfoBody(
    blocks: Sequence[ft.Control],
    *,
    block: str,
    screen: str,
    empty: ft.Control,
    footer: Sequence[ft.Control] = (),
) -> ft.ListView:
    """Return an info page's body: its blocks, else the feed's block, else its empty state.

    One ``ListView`` that scrolls the whole page, at the reading width (720 dp,
    D-305). A plain builder whose one hook is ``use_margin()``, so the page calls it
    once per render; a page whose year data gives its blocks reads nothing of the
    feed and is not re-rendered by a refresh; only the fallback, ``FeedBlock``, reads
    ``Conference`` (D-165's rule for screens that do not show the feed).

    Args:
        blocks: The page's content from its year data, in reading order, each in the
            ``GUTTER`` or a row; empty when the year has no table for the page.
        block: The key of the feed's block that stands in for them
            (``conference.content``: ``wifi``, ``code-of-conduct``, ``venues-hours``,
            ``about``, ``about-psf``, ``social-media``).
        screen: The page's name in semantics identifiers: the feed's block is
            ``<screen>.feed`` (decisions §M).
        empty: What the page shows when neither has anything: its ``EmptyState``,
            which names the way out (ux.md §4.6).
        footer: What ends the page whichever of them shows: Help & safety's Report
            a problem with the app (INFO-11).
    """
    margin = use_margin(READING)
    items = list(blocks) or [FeedBlock(block, screen=screen, empty=empty)]
    items += footer
    return ft.ListView(items, expand=True, padding=sides(margin, top=8, bottom=GUTTER))


@ft.component
def FeedBlock(block: str, *, screen: str, empty: ft.Control) -> ft.Control:
    """Return the feed's block as selectable Markdown, or ``empty`` without one.

    A component of its own, so a refresh that brings a new feed re-renders only this,
    with the new feed's text. A block that is missing or holds no text (a feed before
    the conference publishes it, or the bundled feed of a year without it) is no block.

    Args:
        block: The key of the feed's block (``InfoBody``).
        screen: The page's name in semantics identifiers.
        empty: What shows when the feed has no such block, or no feed is on the device.
    """
    svc = use_services()
    data = use_conference().data
    text = data.content_md.get(block, "") if data is not None else ""
    if not text.strip():
        return empty
    # Its links open by the link rule, as every feed text's do (D-197).
    return feed_markdown(text, svc, identifier=f"{screen}.feed", inset=GUTTER)
