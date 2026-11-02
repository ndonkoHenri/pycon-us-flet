"""The days query, the fold, the word filter and the Speakers order (architecture §7.5).

The questions screens ask of the processed feed are queries: pure functions that never
change the model (SCHED-17) and return new values computed from it. The schedule queries
are in ``timeline.py`` (D-178), Now's and My schedule's in ``agenda.py`` (D-179) and
search in ``search.py`` (D-180); this module holds what the rest of the app shares with
them: the Schedule's days, the one fold, the filter built on it and the order it gives
speakers.
"""

import re
import unicodedata
from collections.abc import Callable
from datetime import date, timedelta

from pycon_us.core.models import ConferenceData, Speaker


def days(data: ConferenceData, first_day: date, last_day: date) -> tuple[date, ...]:
    """Return the Schedule's days: every date of the conference, in order (DATA-17).

    The range runs from the conference's first day to its last (the sprints, which the
    feed has no sessions for), and widens to any schedule day outside it, so no session
    is ever without its day. A day's index is its position here, and it never moves while
    the feed and the year stay the same. Filters play no part (Ionic ignored them too).

    Args:
        data: The processed feed.
        first_day: The conference's first day, from ``conference.toml``.
        last_day: The conference's last day, from ``conference.toml``.

    Returns:
        The dates, one per day, oldest first.
    """
    dates = [day.date for day in data.days]
    start, end = min([first_day, *dates]), max([last_day, *dates])
    return tuple(start + timedelta(days=n) for n in range((end - start).days + 1))


# What NFKD leaves alone but a reader takes as the same text (D-180): typographic quotes
# and dashes, which the feeds use and iOS's smart punctuation types, and letters with a
# stroke or ligatures that Unicode does not decompose. Keys are case folded already.
# Apostrophes, straight, curly or look-alike, are dropped rather than made straight:
# people leave them out when typing on a phone, and "dont" should find "don’t".
_APOSTROPHES = (
    "'"
    "\N{LEFT SINGLE QUOTATION MARK}"
    "\N{RIGHT SINGLE QUOTATION MARK}"
    "\N{SINGLE LOW-9 QUOTATION MARK}"
    "\N{SINGLE HIGH-REVERSED-9 QUOTATION MARK}"
    "\N{PRIME}"
    "\N{MODIFIER LETTER APOSTROPHE}"
    "\N{MODIFIER LETTER TURNED COMMA}"
)
_DOUBLE_QUOTES = (
    "\N{LEFT DOUBLE QUOTATION MARK}"
    "\N{RIGHT DOUBLE QUOTATION MARK}"
    "\N{DOUBLE LOW-9 QUOTATION MARK}"
    "\N{DOUBLE HIGH-REVERSED-9 QUOTATION MARK}"
)
_DASHES = (
    "\N{HYPHEN}\N{FIGURE DASH}\N{EN DASH}\N{EM DASH}\N{HORIZONTAL BAR}\N{MINUS SIGN}"
)
_FOLD_TABLE = str.maketrans(
    {
        **dict.fromkeys(_APOSTROPHES, ""),
        **dict.fromkeys(_DOUBLE_QUOTES, '"'),
        **dict.fromkeys(_DASHES, "-"),
        "ł": "l",
        "ø": "o",
        "đ": "d",
        "ħ": "h",
        "ı": "i",
        "ŧ": "t",
        "æ": "ae",
        "œ": "oe",
    }
)
_NON_ASCII = re.compile(r"[^\x00-\x7f]+")
# Combining and enclosing marks (accents) and invisible format characters (soft hyphen,
# zero-width space and joiner, bidi controls), which would split a word for no reader.
_DROPPED = frozenset({"Mn", "Me", "Cf"})


def fold(text: str) -> str:
    """Return text as search compares it: case, accents and typography folded (D-46, D-180).

    So ``Cristián`` and ``CRISTIAN`` both fold to ``cristian``, ``Straße`` to
    ``strasse``, ``ﬁle`` to ``file``, ``Łukasz`` to ``lukasz``, and ``don’t``, ``don't``
    and ``dont`` all to ``dont``. Feed processing folds ``Session.search_text`` once, ``search`` folds the
    names it indexes and every query the same way, so both sides always agree.

    Args:
        text: Any text.

    Returns:
        The text decomposed (NFKD), case folded and decomposed again, with apostrophes
        removed, typographic double quotes and dashes as ASCII, the letters in
        ``_FOLD_TABLE`` replaced, and marks and format characters removed.
    """
    # NFKD around casefold is the Unicode Standard's compatibility caseless match (§3.13):
    # case folding can leave text that is not decomposed, and folding twice must not
    # change it again. The acute accent, typed as an apostrophe on some Spanish and
    # Portuguese layouts, goes first: NFKD would make it a space and split the word.
    folded = unicodedata.normalize("NFKD", text.replace("\N{ACUTE ACCENT}", ""))
    folded = folded.casefold()
    folded = unicodedata.normalize("NFKD", folded).translate(_FOLD_TABLE)
    # Only non-ASCII runs can hold a mark: checking them alone keeps this fast (D-180).
    return _NON_ASCII.sub(_without_marks, folded)


def _without_marks(run: re.Match[str]) -> str:
    return "".join(c for c in run[0] if unicodedata.category(c) not in _DROPPED)


def matching[T](
    items: tuple[T, ...], query: str, text_of: Callable[[T], str]
) -> tuple[T, ...]:
    """Return the items whose text holds every word of ``query``, each as a substring.

    The query folds as search's does (D-46), and the words may come in any order.

    Screens rely on the identity: a query with no word to match returns ``items``
    itself, not a copy, so ``found is not items`` says that a filter applies. That covers
    a blank query and one that folds to nothing (a lone ``’``).

    Args:
        items: What the filter narrows, in the order shown.
        query: What the user typed in the filter.
        text_of: An item's text, folded by the caller: a text folded once per feed
            version (``search_text``) is not folded again here.

    Returns:
        The items found, in their order; ``items`` itself without a word.
    """
    words = fold(query).split()
    if not words:
        return items
    return tuple(item for item in items if all(word in text_of(item) for word in words))


def speaker_order(speaker: Speaker) -> tuple[str, str]:
    """Return the key that orders speakers as the Speakers list and search show them.

    By displayed name, folded (D-46), then by id, so two people with the same name always
    come out in the same order.

    Args:
        speaker: A speaker of the directory.

    Returns:
        A key for ``sorted``.
    """
    return fold(speaker.name), speaker.id
