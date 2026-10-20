"""The info pages' year data and its checks (D-263).

The info pages (Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF,
Social) say what the year's ``content.toml`` holds for them (D-45, INFO-05): each page's
table is a dataclass here, built through ``year_schema.build()`` as a field of
``config.Content``, and ``check_info()``, which ``config`` runs on every load, checks its
rules. A module of its own, as the Open spaces and Lightning talks pages' is
(``year_pages``, D-205), so ``config.py`` stays under D-66's ~400 lines while the six
pages' tables arrive.

No page has a table yet: each one's issue adds it, with its rules, to this module.
Until a page has its table, or for a year that has none, the page shows the feed's own
block for it (``ui.info_page``).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # config imports this module; the type alone goes the other way
    from pycon_us.config import Content


def check_info(content: Content, file: str) -> None:
    """Check the info pages' tables in a year's content; none has one yet.

    ``config``'s loader calls it with the content it built, after the other pages'
    checks, so a table that breaks a rule fails the load with a ``YearDataError`` that
    names the file and the key, as every year-data error does.

    Args:
        content: The year's ``content.toml``, built.
        file: The data file it comes from, for the messages (``2026/content.toml``).
    """
