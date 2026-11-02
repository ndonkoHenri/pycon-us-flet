"""The year data of the Open spaces and Lightning talks pages, and its checks (D-205).

``content.toml``'s optional ``[open_spaces]`` and ``[lightning_talks]`` tables build into
the dataclasses below, through ``year_schema.build()``, as fields of ``config.Content``.
``check_pages()`` then checks their rules, and ``check_https()`` and ``check_text()`` are the
two checks ``config`` shares with them. Split from ``config.py`` at D-66's ~400 lines.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from pycon_us.year_schema import YearDataError


@dataclass(frozen=True)
class OpenSpacesInfo:
    """What the Open spaces page says of the year's open spaces (EVT-01, EVT-02).

    Attributes:
        intro: One line on what open spaces are and how to host one, at the head of
            each day's list.
        propose_url: Where "Propose an open space" goes: the site's sign-up, opened
            in the in-app browser (INFO-14). Empty when the site has none, a year whose
            site is archived: no button then, so the intro must not offer one.
    """

    intro: str
    propose_url: str = ""


@dataclass(frozen=True)
class Doubt:
    """A reason people give for not giving a lightning talk, and the answer to it.

    Attributes:
        doubt: What they say: "Everyone already knows that".
        answer: Why it holds no one back.
    """

    doubt: str
    answer: str


@dataclass(frozen=True)
class LightningTalksInfo:
    """What the Lightning talks page says of the year's lightning talks (EVT-03).

    Attributes:
        heading: The copy card's heading: "What's a lightning talk?".
        intro: The card's paragraphs, in order: what one is, and when and where they
            happen this year.
        info_url: The site's page on them, the page's "More about lightning talks".
        doubts: "Think you can't do one?": the reasons and their answers, in order.
        signup_url: Where "Sign up for a lightning talk" goes, in the in-app browser.
            Empty when the site has none, a year whose site is archived: no button
            then, so the intro must say how things stand.
    """

    heading: str
    intro: tuple[str, ...]
    info_url: str
    doubts: tuple[Doubt, ...]
    signup_url: str = ""


def check_https(url: str, file: str, key: str) -> None:
    """Refuse a URL that is not ``https://`` with a host.

    Args:
        url: The value to check.
        file: The data file it comes from, for the message (``2026/content.toml``).
        key: Its key in that file, for the message.

    Raises:
        YearDataError: The URL is not ``https://`` or has no host.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise YearDataError(f"{file}: {key}: expected an https:// URL with a host")


def check_text(text: str, file: str, key: str) -> None:
    """Refuse a text that is empty or only white space.

    Args:
        text: The value to check.
        file: The data file it comes from, for the message.
        key: Its key in that file, for the message.

    Raises:
        YearDataError: The text is blank.
    """
    if not text.strip():
        raise YearDataError(f"{file}: {key}: is empty")


def check_pages(
    open_spaces: OpenSpacesInfo | None,
    lightning_talks: LightningTalksInfo | None,
    file: str,
) -> None:
    """Check the two pages' tables: no blank text, ``https://`` links, a fold with doubts.

    Args:
        open_spaces: The ``[open_spaces]`` table, or None when the year has none.
        lightning_talks: The ``[lightning_talks]`` table, or None when the year has none.
        file: The data file they come from, for the messages.

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    if open_spaces is not None:
        check_text(open_spaces.intro, file, "open_spaces.intro")
        if open_spaces.propose_url:
            check_https(open_spaces.propose_url, file, "open_spaces.propose_url")
    if (talks := lightning_talks) is not None:
        check_text(talks.heading, file, "lightning_talks.heading")
        if not talks.intro:
            raise YearDataError(f"{file}: lightning_talks.intro: is empty")
        for index, paragraph in enumerate(talks.intro):
            check_text(paragraph, file, f"lightning_talks.intro[{index}]")
        if talks.signup_url:
            check_https(talks.signup_url, file, "lightning_talks.signup_url")
        check_https(talks.info_url, file, "lightning_talks.info_url")
        if not talks.doubts:  # a fold with nothing in it
            raise YearDataError(f"{file}: lightning_talks.doubts: is empty")
        for index, doubt in enumerate(talks.doubts):
            key = f"lightning_talks.doubts[{index}]"
            check_text(doubt.doubt, file, f"{key}.doubt")
            check_text(doubt.answer, file, f"{key}.answer")
