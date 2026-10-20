"""Slugs, semantics keys and the room sort order (DATA-16, ROOM-06, SPON-02).

``slugify_room`` and ``sponsor_slug`` are copied exactly from Ionic, because routes and
links key on them: each is the only function that makes its kind of slug. They differ on
purpose, as Ionic's did: a sponsor slug keeps a ``-`` for each space, so ``Code & Supply``
is ``code--supply``.

``semantics_key`` makes the key of a semantics identifier (decisions §M). It lives here,
with no Flet, so the year-data loader can check that two labels give two identifiers
(D-283); ``ui.semantics`` re-exports it for the screens.
"""

import re
import unicodedata

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_NUMBER = re.compile(r"(\d+)")
# JavaScript's \s, which Ionic's sponsor slug used: Python's also matches U+001C..U+001F
# and U+0085, and lacks U+FEFF.
_JS_SPACE = re.compile(
    "[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+"
)
_NOT_SPONSOR_SLUG = re.compile(r"[^a-z0-9-]")


def slugify_room(name: str) -> str:
    """Return a room's slug: lower-case, each run of other characters a ``-``, none at the ends.

    ``Room 103ABC`` → ``room-103abc``; ``Pacific Ballroom - Arena`` → ``pacific-ballroom-arena``.
    """
    return _NOT_SLUG.sub("-", name.lower()).strip("-")


def semantics_key(session_id: str) -> str:
    """Return a session id as the key of a semantics identifier (decisions §M).

    A synthetic break id holds spaces and colons (``break-Expo Hall AB-2026-05-15T08:
    00:00-07:00``, D-42), which a UI-test selector would have to match literally; the
    key is lower case, each run of other characters a ``-``:
    ``break-expo-hall-ab-2026-05-15t08-00-00-07-00``. Numeric ids stay as they are.

    Args:
        session_id: The session's id, unchanged everywhere else.
    """
    return _NOT_SLUG.sub("-", session_id.lower()).strip("-")


def sponsor_slug(name: str) -> str:
    """Return a sponsor's slug, Ionic's exactly: lower-case, spaces ``-``, the rest dropped.

    Each run of whitespace becomes one ``-`` and then every character other than
    ``a``..``z``, a digit or ``-`` goes, so ``Qube Research & Technologies`` is
    ``qube-research--technologies`` and ``Anaconda, Inc`` is ``anaconda-inc`` (SPON-02).
    Sponsors have no id: their routes and cross-links use this slug.
    """
    return _NOT_SPONSOR_SLUG.sub("", _JS_SPACE.sub("-", name.lower()))


def room_sort_key(name: str) -> tuple[tuple[int, int, str], ...]:
    """Return a key that sorts room names naturally, ignoring case and accents.

    Numbers compare by value, so ``Room 102A`` comes before ``Room 1000``, as Ionic's
    ``localeCompare(..., {numeric: true, sensitivity: "base"})`` sorted them. Accents are
    ignored where Unicode decomposes them (``é`` sorts as ``e``); a letter such as ``ø``
    or ``ł`` keeps its own place after ``z``. Room names are English, so that is enough.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in _NUMBER.split(folded)
        if part
    )
