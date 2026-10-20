"""The info pages' year data and its checks (D-263).

The info pages (Wi-Fi, Help & safety, Venue & hours, About PyCon US, About the PSF,
Social) say what the year's ``content.toml`` holds for them (D-45, INFO-05): each page's
table is a dataclass here, built through ``year_schema.build()`` as a field of
``config.Content``, and ``check_info()``, which ``config`` runs on every load, checks its
rules. A module of its own, as the Open spaces and Lightning talks pages' is
(``year_pages``, D-205), so ``config.py`` stays under D-66's ~400 lines while the six
pages' tables arrive.

Each page's issue adds its table, with its rules, to this module: so far Wi-Fi's
(``WifiInfo``, D-280) and About the PSF's (``PsfInfo``, D-283). Until a page has its
table, or for a year that has none, the page shows the feed's own block for it
(``ui.info_page``).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pycon_us.core.slugs import semantics_key
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

if TYPE_CHECKING:  # config imports this module; the type alone goes the other way
    from pycon_us.config import Content


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
    if content.psf is not None:
        check_psf(content.psf, file)


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
