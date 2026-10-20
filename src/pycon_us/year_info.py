"""The info pages' year data and its checks (D-263).

The info pages (Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF,
Social) say what the year's ``content.toml`` holds for them (D-45, INFO-05): each page's
table is a dataclass here, built through ``year_schema.build()`` as a field of
``config.Content``, and ``check_info()``, which ``config`` runs on every load, checks its
rules. A module of its own, as the Open spaces and Lightning talks pages' is
(``year_pages``, D-205), so ``config.py`` stays under D-66's ~400 lines while the six
pages' tables arrive.

Each page's issue adds its table, with its rules, to this module: so far Wi-Fi's
(``WifiInfo``, D-280), Help & safety's, About the PSF's (``PsfInfo``, D-283) and Social's
(``SocialInfo``, D-284). Until a page has its table, or for a year that has none, the
page shows the feed's own block for it (``ui.info_page``).

Help & safety (D-281): ``[[safety_contacts]]`` (``SafetyContact``), the ways to report
a concern, each with the public page that shows it and the day someone checked it
there, and ``[help]`` (``HelpInfo``), the page's other lines and links.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from pycon_us.core.slugs import semantics_key
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

if TYPE_CHECKING:  # config imports this module; the type alone goes the other way
    from pycon_us.config import Content

CONTACT_KINDS = ("tel", "mailto", "https")
"""What a safety contact can be: a phone number, an email address or a web page."""

E164 = re.compile(r"\+[1-9]\d{6,14}")
"""A phone number in E.164: ``+``, a country code and the number, digits only."""

EMAIL = re.compile(r"[^@\s:/?#]+@[^@\s:/?#]+\.[^@\s:/?#.]+")
"""An email address: a local part, ``@``, and a host name with a dot."""


@dataclass(frozen=True)
class SafetyContact:
    """A way to report a concern, on Help & safety's Report a concern card (INFO-07).

    Safety-critical, so each one names the public page that shows it and the day
    someone last checked it there (D-45): a number found only in Ionic's code stays out.

    Attributes:
        label: What a tap does, as the row's title: "Email the Code of Conduct team".
        kind: ``tel``, ``mailto`` or ``https``; it names the row's identifier
            (``help.report.<kind>``), so a year lists each kind once.
        value: The number in E.164 (``+15625550100``), the address, or the ``https``
            URL.
        source: The public ``https`` page that shows the value.
        checked: The day the value was last checked on ``source``.
    """

    label: str
    kind: str
    value: str
    source: str
    checked: date

    @property
    def target(self) -> str:
        """The link a tap opens: ``tel:+1…``, ``mailto:…`` or the web page."""
        return self.value if self.kind == "https" else f"{self.kind}:{self.value}"


@dataclass(frozen=True)
class HelpInfo:
    """Help & safety's lines and links beside the contacts (INFO-07, INFO-11).

    Attributes:
        in_person: The card's last line: in danger, local emergency services first,
            with staff to help find the number; then reporting to any staff member.
        info_desk: Where the information desk is, in one line.
        lost_and_found: Where lost items go, in one line.
        quiet_room: Where the quiet room is, in one line.
        coc_summary: The Code of Conduct in a few sentences, in our words.
        coc_url: The full Code of Conduct, "Read the Code of Conduct".
        procedures_url: How reports are handled, "How reports are handled".
    """

    in_person: str
    info_desk: str
    lost_and_found: str
    quiet_room: str
    coc_summary: str
    coc_url: str
    procedures_url: str


@dataclass(frozen=True)
class WifiInfo:
    """The conference network the Wi-Fi page shows and copies (INFO-08, D-280).

    Attributes:
        network: The network's name (its SSID), exactly as a phone lists it.
        password: Its password, exactly as it is typed.
    """

    network: str
    password: str


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
    if (wifi := content.wifi) is not None:
        # A blank value would show nothing to read, and copy nothing to paste.
        check_text(wifi.network, file, "wifi.network")
        check_text(wifi.password, file, "wifi.password")
    check_safety_contacts(content.safety_contacts, file)
    if content.help is not None:
        # The page's first stop is the card, and in_person is on it: a [help] without
        # a contact would leave the page with no way to report (D-281).
        if not content.safety_contacts:
            raise YearDataError(
                f"{file}: help: needs at least one [[safety_contacts]] entry"
                " (the Report a concern card)"
            )
        check_help(content.help, file)
    if content.psf is not None:
        check_psf(content.psf, file)
    check_social(content.social, file)


def check_safety_contacts(contacts: tuple[SafetyContact, ...], file: str) -> None:
    """Check the safety contacts: a label, a well-formed value, an https source.

    ``build()`` already refuses a contact without ``source`` or ``checked``.

    Args:
        contacts: The ``[[safety_contacts]]`` entries.
        file: The data file they come from, for the messages.

    Raises:
        YearDataError: A rule is broken, or two contacts share a kind.
    """
    seen: set[str] = set()
    for index, contact in enumerate(contacts):
        key = f"safety_contacts[{index}]"
        check_text(contact.label, file, f"{key}.label")
        if contact.kind not in CONTACT_KINDS:
            raise YearDataError(
                f"{file}: {key}.kind: {contact.kind!r} is not one of {CONTACT_KINDS}"
            )
        if contact.kind in seen:  # one row, one identifier per kind
            raise YearDataError(f"{file}: {key}.kind: duplicate kind {contact.kind!r}")
        seen.add(contact.kind)
        check_contact_value(contact, file, f"{key}.value")
        check_https(contact.source, file, f"{key}.source")


def check_contact_value(contact: SafetyContact, file: str, key: str) -> None:
    """Refuse a value its kind cannot open: a number not in E.164, a bad address.

    Args:
        contact: The contact whose value to check, by its kind.
        file: The data file it comes from, for the message.
        key: Its key in that file, for the message.

    Raises:
        YearDataError: The value is malformed for its kind.
    """
    if contact.kind == "https":
        check_https(contact.value, file, key)
    elif contact.kind == "tel" and not E164.fullmatch(contact.value):
        raise YearDataError(f"{file}: {key}: expected an E.164 number (+15625550100)")
    elif contact.kind == "mailto" and not EMAIL.fullmatch(contact.value):
        raise YearDataError(f"{file}: {key}: expected an email address")


def check_help(info: HelpInfo, file: str) -> None:
    """Check ``[help]``: no blank line, ``https://`` links.

    Args:
        info: The ``[help]`` table.
        file: The data file it comes from, for the messages.

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    for name in ("in_person", "info_desk", "lost_and_found", "quiet_room"):
        check_text(getattr(info, name), file, f"help.{name}")
    check_text(info.coc_summary, file, "help.coc_summary")
    check_https(info.coc_url, file, "help.coc_url")
    check_https(info.procedures_url, file, "help.procedures_url")


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
