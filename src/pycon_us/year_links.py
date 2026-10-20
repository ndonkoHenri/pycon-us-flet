"""About the PSF's and Social's year data, the info pages of links, and their checks.

About the PSF's ``[psf]`` (``PsfInfo``, ``PsfLink``, D-283) and Social's ``[social]``
(``SocialInfo``, ``SocialLink``, D-284) are lists of links that leave the app, each
row with its identifier and its brand mark or icon. ``year_info.check_info()``, which
``config`` runs on every load, calls their checks. A module of their own, split from
``year_info.py`` at D-66's ~400 lines (#532).
"""

import re
from dataclasses import dataclass

from pycon_us.core.slugs import semantics_key
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

PSF_SECTIONS = ("get_involved", "python_resources", "follow")
"""About the PSF's sections, in the page's order (ux.md §6.7): a link names its own."""


@dataclass(frozen=True)
class PsfLink:
    """A link on About the PSF (INFO-06, D-283): a row that leaves the app.

    Attributes:
        section: Which of ``PSF_SECTIONS`` lists it.
        label: The row's title, in sentence case: "Become a member".
        url: Where it goes, ``https://`` only.
        brand: The brand mark beside it (a key of ``ui.brands.BRANDS``), for a link to
            that brand only (D-264); None for none.
        icon: An outlined ``ft.Icons`` name beside it instead, for a link with no brand
            of its own (D-27); None for none.
        app: The link is a social profile, which opens in its own app (INFO-14).
    """

    section: str
    label: str
    url: str
    brand: str | None = None
    icon: str | None = None
    app: bool = False


@dataclass(frozen=True)
class PsfInfo:
    """What About the PSF shows (INFO-06, D-283): the mission once, Donate, the links.

    Attributes:
        mission: The PSF's mission statement, as the PSF words it.
        donate_url: Where "Donate to the PSF" goes, ``https://`` only.
        links: The page's rows, each under its section, in the order given.
    """

    mission: str
    donate_url: str
    links: tuple[PsfLink, ...] = ()


def check_psf(psf: PsfInfo, file: str) -> None:
    """Check ``[psf]``: no blank text, ``https://`` only, known sections, one row per key.

    A row's identifier is ``psf.link.<semantics_key(label)>`` (D-33), so two labels
    that give one key ("PSF blog", "PSF Blog") are refused, as is a label with no
    letter or digit, whose key is empty. A brand or an icon names something the page
    draws, so ``tests/test_year_info.py``'s
    ``test_psf_brands_are_bundled_marks_and_icons_are_material_icons`` checks every
    bundled year's names against ``ui.brands`` and ``ft.Icons``, as the tracks' icons
    are (the loader imports nothing from Flet).

    Args:
        psf: The ``[psf]`` table.
        file: The data file it comes from, for the messages.

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    check_text(psf.mission, file, "psf.mission")
    check_https(psf.donate_url, file, "psf.donate_url")
    labels: dict[str, str] = {}  # each row key, with the label that gave it
    for index, link in enumerate(psf.links):
        key = f"psf.links[{index}]"
        if link.section not in PSF_SECTIONS:
            raise YearDataError(
                f"{file}: {key}.section: unknown section {link.section!r}, expected "
                "get_involved, python_resources or follow"
            )
        check_text(link.label, file, f"{key}.label")
        # The label gives the row's identifier, which must name one row (D-33).
        row_key = semantics_key(link.label)
        if not row_key:
            raise YearDataError(
                f"{file}: {key}.label: {link.label!r} has no letter or digit for its key"
            )
        if row_key in labels:
            raise YearDataError(
                f"{file}: {key}.label: {link.label!r} gives the same identifier as "
                f"{labels[row_key]!r}"
            )
        labels[row_key] = link.label
        check_https(link.url, file, f"{key}.url")
        if link.brand is not None and link.icon is not None:
            raise YearDataError(f"{file}: {key}: give a brand or an icon, not both")


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
