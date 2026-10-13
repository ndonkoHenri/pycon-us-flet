"""Read-only questions screens ask of the processed feed (architecture §7.5).

Queries never change the model (SCHED-17): they return new values computed from it.
"""

import re
import unicodedata
from datetime import date, timedelta

from pycon_us.core.models import ConferenceData


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
_SINGLE_QUOTES = (
    "\N{LEFT SINGLE QUOTATION MARK}"
    "\N{RIGHT SINGLE QUOTATION MARK}"
    "\N{SINGLE LOW-9 QUOTATION MARK}"
    "\N{SINGLE HIGH-REVERSED-9 QUOTATION MARK}"
    "\N{PRIME}"
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
        **dict.fromkeys(_SINGLE_QUOTES, "'"),
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
    ``strasse``, ``ﬁle`` to ``file``, ``Łukasz`` to ``lukasz`` and ``don’t`` to
    ``don't``. Feed processing folds ``Session.search_text`` once, ``search`` folds the
    names it indexes and every query the same way, so both sides always agree.

    Args:
        text: Any text.

    Returns:
        The text decomposed (NFKD), case folded and decomposed again, with typographic
        quotes and dashes as ASCII, the letters in ``_FOLD_TABLE`` replaced, and marks
        and format characters removed.
    """
    # NFKD around casefold is the Unicode Standard's compatibility caseless match (§3.13):
    # case folding can leave text that is not decomposed, and folding twice must not
    # change it again.
    folded = unicodedata.normalize("NFKD", text).casefold()
    folded = unicodedata.normalize("NFKD", folded).translate(_FOLD_TABLE)
    # Only non-ASCII runs can hold a mark: checking them alone keeps this fast (D-180).
    return _NON_ASCII.sub(_without_marks, folded)


def _without_marks(run: re.Match[str]) -> str:
    return "".join(c for c in run[0] if unicodedata.category(c) not in _DROPPED)
