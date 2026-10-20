"""Job listings: their roles, what search matches, and their sponsors (SPON-09; D-278).

Sponsors write their listings as HTML in three shapes, and ``parse_roles()`` reads two of
them as links, where Ionic linked a role only when its URL was the anchor's text
(Bloomberg: 15 roles, 0 links):

- **Anchors** (Bloomberg, Temporal, NVIDIA, Sentry, Old Mission, Tower Research): each
  ``<a href>`` is a role, titled by its text.
- **Bare URLs** (Hudson River Trading's ``Title | URL`` items; Anaconda's, Capital One's
  and Qube's careers page alone in a paragraph): a list item or paragraph without an
  anchor that holds one bare ``http(s)`` URL is a role, titled by the text before the
  URL, else by the URL's last segment, as Ionic's ``shortenUrl`` did.
- **Long form** (SerpApi, marimo): a listing with a heading is a written job description,
  not a list of roles. It gets no roles, and its Markdown shows instead.

A placeholder such as ``N/A`` (OpenEDG) is no roles and no description
(``is_placeholder``). ``feed.process()`` reads each listing once (``read_listing``), and
the screens find a sponsor's listings by its exact name (``listings_of``).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from pycon_us.core import html_md
from pycon_us.core.links import feed_link
from pycon_us.core.models import ConferenceData, JobListing, Role, Sponsor
from pycon_us.core.queries import fold

_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BLOCKS = frozenset({"p", "li"})  # where a bare URL makes a role
# Where a browser starts a new line: the text on either side is not one word, nor one URL.
_BREAKS = frozenset(
    {"br", "hr", "div", "ul", "ol", "dl", "dt", "dd", "blockquote", "pre", "table"}
    | {"tr", "td", "th", "section", "article", "header", "footer", *_BLOCKS, *_HEADINGS}
)
_WEB_SCHEMES = frozenset({"http", "https"})  # a role opens a page; mailto: is no role

# A bare URL as D-114 finds one: sentence punctuation after it is not part of it.
_URL = re.compile(r"https?://[^\s<>\"]+")
_URL_TRAILER = re.compile(r"[.,;:!?'\")\]’”]+$")

_SEPARATORS = " |:,;-–—·"
"""Trimmed off the text before a bare URL: ``Research Engineer | https://…``."""

_PLACEHOLDERS = frozenset({"", "na", "none", "tba", "tbd"})
"""A listing's whole text, folded and without punctuation, that says nothing."""


def parse_roles(html: str, site_url: str) -> tuple[Role, ...]:
    """Return the roles a listing's HTML links to, in its order (SPON-09, D-278).

    An anchor is a role, titled by its text, or by its URL's last segment when its text
    is empty or a URL. A list item or paragraph without an anchor that holds exactly one
    bare ``http(s)`` URL is a role, titled by the text before the URL, its separators
    trimmed, else by the URL's last segment. A line break or a block's edge separates
    words and URLs, and ``script`` and ``style`` text is not read, as in ``html_md``. A
    listing with a heading is long form and has none. A link is what ``feed_link()``
    makes of it (a site path joins the year's site); only ``http`` and ``https`` links
    are roles.

    Args:
        html: The listing's ``description_html``.
        site_url: The year's site, which a site-relative link joins.

    Returns:
        The roles; empty for a long-form listing or one that links nothing.
    """
    parser = _RoleParser(site_url)
    parser.feed(html)
    parser.close()
    return () if parser.long_form else parser.roles()


def is_placeholder(text: str) -> bool:
    """Return whether a listing's text says nothing: blank, ``-``, ``N/A`` and the like.

    Args:
        text: The listing's visible text (``html_md.to_text``).
    """
    return re.sub(r"[\W_]+", "", fold(text)) in _PLACEHOLDERS


def read_listing(
    listing: JobListing, site_url: str, markdown: Callable[[str], str]
) -> JobListing:
    """Return the listing with its Markdown, roles and search text (D-140, D-278).

    A placeholder keeps no Markdown and gets no roles, and only the sponsor's name
    matches it.

    Args:
        listing: The listing as decoded.
        site_url: The year's site, which relative links join.
        markdown: ``feed.process()``'s converter, which converts each value once.
    """
    text = html_md.to_text(listing.description)
    if is_placeholder(text):
        return replace(listing, search_text=fold(listing.sponsor_name))
    roles = parse_roles(listing.description, site_url)
    titles = [role.title for role in roles]
    return replace(
        listing,
        description_md=markdown(listing.description),
        roles=roles,
        search_text=fold(" ".join([listing.sponsor_name, *titles, text])),
    )


def listings_of(data: ConferenceData, sponsor: Sponsor) -> tuple[JobListing, ...]:
    """Return the sponsor's job listings: those naming it exactly, in feed order (SPON-05).

    Listings carry the sponsor's name, not its slug, and ``tools/feed_invariants.py``
    checks that every listing names a sponsor. Thirteen listings need no index.

    Args:
        data: The processed feed.
        sponsor: The sponsor.
    """
    return tuple(j for j in data.job_listings if j.sponsor_name == sponsor.name)


@dataclass
class _Anchor:
    """An open ``<a>``: its ``href`` and the text read so far."""

    href: str | None
    start: int  # where it starts in the listing's text
    text: list[str] = field(default_factory=list)


@dataclass
class _Block:
    """An open ``<p>`` or ``<li>``: its own text, and whether it holds an anchor.

    Each piece of text keeps where it starts in the listing's text, so that a role found
    when the block ends still sorts by where its URL was.
    """

    tag: str
    pieces: list[tuple[int, str]] = field(default_factory=list)
    has_anchor: bool = False

    def offset(self, index: int) -> int:
        """Return where the block's text at ``index`` is in the listing's text."""
        for start, piece in self.pieces:
            if index < len(piece):
                return start + index
            index -= len(piece)
        raise IndexError(index)


class _RoleParser(HTMLParser):
    """Collects a listing's roles as ``parse_roles()`` describes, and its headings."""

    def __init__(self, site_url: str) -> None:
        """Start with no role; links join ``site_url``."""
        super().__init__(convert_charrefs=True)
        self.site_url = site_url
        self.long_form = False
        # Each role with where it starts in the listing's text: an inner block ends,
        # and adds its role, before the block around it, so roles sort by it.
        self._found: list[tuple[int, Role]] = []
        self._read = 0  # how much of the listing's text has been read
        self._blocks: list[_Block] = []  # the open blocks, innermost last
        self._anchor: _Anchor | None = None
        self._dropping: str | None = None  # the script or style element being skipped

    def roles(self) -> tuple[Role, ...]:
        """Return the roles found, in the listing's order."""
        return tuple(role for _, role in sorted(self._found, key=lambda f: f[0]))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Note a heading, open a block, or open an anchor in every open block."""
        if tag in html_md.DROPPED_TAGS:
            self._dropping = tag
            return
        if tag in _BREAKS:
            self.handle_data(" ")  # before a block opens, so it ends the text around it
        if tag in _HEADINGS:
            self.long_form = True
        elif tag in _BLOCKS:
            self._blocks.append(_Block(tag))
        elif tag == "a":
            self._end_anchor()  # anchors never nest: a new one ends the last
            self._anchor = _Anchor(dict(attrs).get("href"), self._read)
            for block in self._blocks:
                block.has_anchor = True

    def handle_endtag(self, tag: str) -> None:
        """End the anchor, or the block and any block left open inside it."""
        if tag == self._dropping:
            self._dropping = None
        elif tag == "a":
            self._end_anchor()
        elif tag in _BLOCKS and any(block.tag == tag for block in self._blocks):
            while (block := self._blocks.pop()).tag != tag:
                self._end_block(block)
            self._end_block(block)
        if tag in _BREAKS:
            self.handle_data(" ")  # after a block closes, so it ends the text around it

    def handle_data(self, data: str) -> None:
        """Add text to the open anchor and to the innermost open block."""
        if self._dropping is not None:
            return
        if self._anchor is not None:
            self._anchor.text.append(data)
        if self._blocks:
            self._blocks[-1].pieces.append((self._read, data))
        self._read += len(data)

    def close(self) -> None:
        """End what the HTML left open, innermost first."""
        super().close()
        self._end_anchor()
        while self._blocks:
            self._end_block(self._blocks.pop())

    def _end_anchor(self) -> None:
        """Make the open anchor a role when it links to a web page."""
        anchor, self._anchor = self._anchor, None
        if anchor is None or (url := self._web_link(anchor.href)) is None:
            return
        title = " ".join("".join(anchor.text).split())
        if not title or _URL.fullmatch(title):
            title = _url_title(url)
        self._found.append((anchor.start, Role(title, url)))

    def _end_block(self, block: _Block) -> None:
        """Make a block without an anchor a role when it holds one bare URL."""
        if block.has_anchor:
            return
        text = "".join(piece for _, piece in block.pieces)
        matches = list(_URL.finditer(text))
        if len(matches) != 1:
            return
        url = self._web_link(_URL_TRAILER.sub("", matches[0].group()))
        if url is None:
            return
        title = " ".join(text[: matches[0].start()].split()).strip(_SEPARATORS)
        role = Role(title or _url_title(url), url)
        self._found.append((block.offset(matches[0].start()), role))

    def _web_link(self, href: str | None) -> str | None:
        """Return the ``http(s)`` address ``href`` stands for, or None without a host."""
        link = feed_link(href, self.site_url)
        if link is None:
            return None
        parts = urlsplit(link)
        return link if parts.scheme.lower() in _WEB_SCHEMES and parts.hostname else None


def _url_title(url: str) -> str:
    """Title a role by its URL's last path segment, as Ionic's ``shortenUrl`` did.

    ``…/about-us/careers`` is "Careers" and ``…/python-jobs`` "Python jobs": the segment
    decoded, its dashes and underscores spaces, its first letter upper-cased. A URL
    without a path is titled by its host.
    """
    parts = urlsplit(url)
    segment = next((s for s in reversed(parts.path.split("/")) if s), "")
    title = " ".join(unquote(segment).replace("-", " ").replace("_", " ").split())
    if not title:
        return parts.hostname or url
    return title[:1].upper() + title[1:]
