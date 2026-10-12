"""Room slugs and the room sort order (DATA-16, ROOM-06).

``slugify_room`` is copied exactly from Ionic, because room routes and links key on it: it
is the only function that makes a room slug.
"""

import re
import unicodedata

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_NUMBER = re.compile(r"(\d+)")


def slugify_room(name: str) -> str:
    """Return a room's slug: lower-case, each run of other characters a ``-``, none at the ends.

    ``Room 103ABC`` → ``room-103abc``; ``Pacific Ballroom - Arena`` → ``pacific-ballroom-arena``.
    """
    return _NOT_SLUG.sub("-", name.lower()).strip("-")


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
