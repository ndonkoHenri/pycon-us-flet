"""The info pages' year data and its checks (D-263).

The info pages (Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF,
Social) say what the year's ``content.toml`` holds for them (D-45, INFO-05): each page's
table is a dataclass here, built through ``year_schema.build()`` as a field of
``config.Content``, and ``check_info()``, which ``config`` runs on every load, checks its
rules. A module of its own, as the Open spaces and Lightning talks pages' is
(``year_pages``, D-205), so ``config.py`` stays under D-66's ~400 lines while the six
pages' tables arrive.

Each page's issue adds its table, with its rules, to this module: so far Social's
(``SocialInfo``, D-284). Until a page has its table, or for a year that has none, the
page shows the feed's own block for it (``ui.info_page``).
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

if TYPE_CHECKING:  # config imports this module; the type alone goes the other way
    from pycon_us.config import Content


def check_info(content: Content, file: str) -> None:
    """Check the info pages' tables in a year's content.

    ``config``'s loader calls it with the content it built, after the other pages'
    checks, so a table that breaks a rule fails the load with a ``YearDataError`` that
    names the file and the key, as every year-data error does.

    Args:
        content: The year's ``content.toml``, built.
        file: The data file it comes from, for the messages (``2026/content.toml``).

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    check_social(content.social, file)


SOCIAL_SECTIONS = {
    "pycon": "PyCon US",
    "psf": "Python Software Foundation",
    "blogs": "Blogs",
}
"""The Social page's sections of links, by ``section`` key, in the page's order, with
their headings (INFO-10, D-284). A profile (``pycon``, ``psf``) opens in its app, a
blog in the in-app browser (ux.md §4.7)."""

_HASHTAG = re.compile(r"#\w+")
"""A hashtag as the networks read one: ``#`` then letters, digits or ``_``."""

_BRAND = re.compile(r"[a-z]+")
"""A brand mark's key, the name of its SVG (``ui.brands.BRANDS``, D-264)."""


@dataclass(frozen=True)
class SocialLink:
    """A profile or a blog on the Social page (INFO-10, D-284).

    Attributes:
        section: Which section lists it, a key of ``SOCIAL_SECTIONS``.
        label: The row's title, the network or the blog: "Mastodon", "PSF blog".
        handle: The row's second line, where it is: "@pycon@fosstodon.org",
            "pyfound.blogspot.com".
        url: Where a tap goes, ``https://`` only.
        brand: The key of its brand mark in ``ui.brands.BRANDS`` ("mastodon"); empty
            for a blog without one, whose row shows a feed icon. The loader stays
            free of Flet, so a test checks it names a mark (as for the track icons).
    """

    section: str
    label: str
    handle: str
    url: str
    brand: str = ""

    @property
    def key(self) -> str:
        """The link's key in its identifier, ``social.link.<key>``: ``pycon_mastodon``."""
        words = re.findall(r"[a-z0-9]+", self.label.lower())
        return "_".join((self.section, *words))


@dataclass(frozen=True)
class SocialInfo:
    """What the Social page shows: the hashtags to copy, then the links (INFO-10).

    Attributes:
        hashtags: The conference's hashtags, with their ``#``, in the page's order.
        links: The profiles and blogs, each in its section, in the page's order
            within it.
    """

    hashtags: tuple[str, ...]
    links: tuple[SocialLink, ...]


def check_social(social: SocialInfo | None, file: str) -> None:
    """Check the ``[social]`` table: real hashtags, known sections, ``https://`` links.

    Args:
        social: The table, or None when the year has none.
        file: The data file it comes from, for the messages.

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    if social is None:
        return
    if not social.hashtags and not social.links:  # a page of nothing
        raise YearDataError(f"{file}: social: is empty")
    for index, hashtag in enumerate(social.hashtags):
        if not _HASHTAG.fullmatch(hashtag):
            raise YearDataError(
                f"{file}: social.hashtags[{index}]: {hashtag!r} is not a hashtag"
            )
        if hashtag.lower() in (seen.lower() for seen in social.hashtags[:index]):
            raise YearDataError(
                f"{file}: social.hashtags[{index}]: duplicate hashtag {hashtag!r}"
            )
    keys: set[str] = set()
    for index, link in enumerate(social.links):
        key = f"social.links[{index}]"
        if link.section not in SOCIAL_SECTIONS:
            raise YearDataError(
                f"{file}: {key}.section: {link.section!r} is not one of "
                f"{tuple(SOCIAL_SECTIONS)}"
            )
        check_text(link.label, file, f"{key}.label")
        check_text(link.handle, file, f"{key}.handle")
        check_https(link.url, file, f"{key}.url")
        if link.brand and not _BRAND.fullmatch(link.brand):
            raise YearDataError(f"{file}: {key}.brand: {link.brand!r} is not a key")
        if link.key in keys:  # two rows would share an identifier
            raise YearDataError(
                f"{file}: {key}.label: {link.label!r} is already in {link.section!r}"
            )
        keys.add(link.key)
