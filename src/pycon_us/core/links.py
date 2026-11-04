"""What a link in a feed text stands for: `feed_link()` (D-197, D-278).

A link in a feed text is what its author wrote, so `feed_link()` says which web or mail
address it stands for, if any: only `http`, `https` and `mailto` links open, a
site-relative path joins the year's site, and a web address written without its scheme
(2026's `[pytest](pytest.org)`) gets `https://`. It is pure, so both sides use the one
rule: the screens, when a link in a feed text is tapped (`ui/links.py`'s
`open_feed_link()`, a sprint's project page), and feed processing, when it reads a job
listing's roles (`core/jobs.py`).
"""

import re
from urllib.parse import urljoin, urlsplit

FEED_LINK_SCHEMES = ("http", "https", "mailto")
"""The schemes a link in a feed text may have to open (D-197)."""

_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", re.IGNORECASE)
"""A host name with a dot and a top-level domain of letters: `pytest.org`."""


def feed_link(href: str | None, site_url: str) -> str | None:
    """Return the address a link in a feed text opens, or None when it opens nothing.

    Descriptions converted from the feed's HTML have absolute links already (D-114);
    open-space descriptions are Markdown with their links as their authors wrote them
    (D-140), so this decides what each form means (D-197):

    - `http`, `https` and `mailto` links are themselves; any other scheme
      (`javascript:`, `file:`, `tel:`) opens nothing.
    - A path from the site's root (`/2026/sponsors/`), or from a host without a
      scheme (`//host/…`), joins the year's site URL, as it would on the site.
    - A web address written without its scheme, its first segment a host name
      (`pytest.org`, `docs.pytest.org/en/stable/`), gets `https://`, as a
      browser's address bar would: joined to the site URL it would be a page of the
      site that does not exist.
    - Anything else (`#top`, `../slides`, `notes`) depends on the page the text
      was written on, which the app does not know, so it opens nothing.

    Args:
        href: The link's destination: as `Markdown`'s `on_tap_link` gives it, or a
            job listing's anchor's `href`.
        site_url: The year's site, ending in `/` (`ConferenceInfo.site_url`).

    Returns:
        A `http`, `https` or `mailto` URL, or None.
    """
    target = (href or "").strip()
    if not target:
        return None
    try:
        if target.startswith("/"):
            return urljoin(site_url, target)
        scheme = urlsplit(target).scheme.lower()
    except ValueError:  # an address urlsplit cannot read, e.g. "http://[" or "//["
        return None
    if scheme:
        return target if scheme in FEED_LINK_SCHEMES else None
    host = re.split(r"[/?#]", target, maxsplit=1)[0]
    return f"https://{target}" if _HOST.fullmatch(host) else None
