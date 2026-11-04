"""The Speakers list's query: the directory by letter, each with its first session.

`directory()` turns the processed feed's speaker directory into the list's entries,
once per feed version, in the order D-46 gives it (`queries.speaker_order`: by
displayed name, folded, then by id); each entry knows its letter, its first session and
how many more it has (SPKR-01, DATA-21). `letter_groups()` cuts them into the list's
sections, and `filter_directory()` keeps the entries a filter finds, with search's own
matching (`search.search`, D-180), so no screen folds or matches on its own.
`speaker_sessions()` is a speaker's page's list (SPKR-03): their sessions by day, in
the order the list's first session comes from; `has_bio()` says whether the page has a
bio to show.

Pseudo-speakers ("Hosted by …") never reach the directory: feed processing keeps them as
text only (D-125), so the list has nothing to leave out.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby

from pycon_us.core.html_md import to_text
from pycon_us.core.models import ConferenceData, Session, Speaker
from pycon_us.core.queries import fold, speaker_order
from pycon_us.core.search import SearchIndex, search
from pycon_us.core.timeline import DaySessions, schedule_order

NO_LETTER = "#"
"""The heading of a name with nothing to fold, which a feed should never send."""


@dataclass(frozen=True)
class SpeakerEntry:
    """One row of the Speakers list: a speaker, its letter and its first session.

    A value: two entries of the same speaker and session objects are equal, and the
    model's objects compare by identity, so comparing entries never walks a session.
    That is what lets a memoised row or section skip its body (D-153, F34).

    Attributes:
        speaker: The directory speaker.
        letter: The heading it is listed under (`letter_of()`).
        first_session: Its first session in the Schedule's order, the day first; None
            for a speaker with none, which neither recorded feed has.
        more: How many other sessions it has: the row's "+1 more".
    """

    speaker: Speaker
    letter: str
    first_session: Session | None
    more: int


@dataclass(frozen=True)
class LetterGroup:
    """The speakers under one letter heading, in the list's order.

    Attributes:
        letter: The heading, e.g. `A` or `Ж`.
        entries: The entries, never empty.
    """

    letter: str
    entries: tuple[SpeakerEntry, ...]


def letter_of(name: str) -> str:
    """Return the heading a name is listed under: its folded first character (D-46).

    The fold is search's (`queries.fold`), so `Élodie` is under E, `Łukasz` under
    L and `Ömer` under O; a letter without a Latin base keeps its own heading
    (`Жанна` under Ж, `张伟` under 张), after Z in D-46's order. Taking the first
    character of the very text the list is sorted by keeps every heading's speakers
    together in that order, whatever the first character is.

    Args:
        name: A displayed name.

    Returns:
        One upper-case character, or `NO_LETTER` for a name that folds to nothing.
    """
    return fold(name)[:1].upper() or NO_LETTER


def initials(name: str) -> str:
    """Return a speaker's initials for an avatar: the first and last words' first letters.

    Upper-cased. Words without a letter (a dash, an emoji) are skipped, and accents stay,
    as the name shows them: `Lía Da Silva - Rojas` gives `LR`, `Łukasz Langa`
    `ŁL`, `Amethyst Reese 🌸` `AR`; a one-word name gives one letter (`张伟`
    gives 张).

    Args:
        name: A displayed name.

    Returns:
        One or two letters; empty for a name without a letter.
    """
    letters = [
        next(char for char in word if char.isalpha())
        for word in unicodedata.normalize("NFC", name).split()
        if any(char.isalpha() for char in word)
    ]
    if not letters:
        return ""
    return (letters[0] + letters[-1] if len(letters) > 1 else letters[0]).upper()


def directory(data: ConferenceData) -> tuple[SpeakerEntry, ...]:
    """Return the Speakers list's entries: every directory speaker, in D-46's order.

    Build it once per feed version. A speaker's sessions are every session that links
    it (DATA-15), poster details included, in the Schedule's order with the day first
    (`schedule_order`).

    Args:
        data: The processed feed.

    Returns:
        One entry per speaker, by `speaker_order`.
    """
    sessions: dict[str, list[Session]] = {}
    for session in data.sessions.values():
        for speaker_id in session.speaker_ids:
            sessions.setdefault(speaker_id, []).append(session)
    entries = []
    for speaker in sorted(data.speakers.values(), key=speaker_order):
        own = sorted(sessions.get(speaker.id, ()), key=_listing_order)
        entries.append(
            SpeakerEntry(
                speaker=speaker,
                letter=letter_of(speaker.name),
                first_session=own[0] if own else None,
                more=max(len(own) - 1, 0),
            )
        )
    return tuple(entries)


def speaker_sessions(data: ConferenceData, speaker_id: str) -> tuple[DaySessions, ...]:
    """Return a speaker's sessions by conference-local day, for their page (SPKR-03).

    Every session that links the speaker (DATA-15), poster details included, in the
    Schedule's order with the day first: the order `directory()` takes the Speakers
    list's first session from, so the list and the page agree.

    Args:
        data: The processed feed.
        speaker_id: The speaker's id; an unknown one has no sessions.

    Returns:
        One group per day with sessions, oldest first; empty for none.
    """
    own = sorted(
        (s for s in data.sessions.values() if speaker_id in s.speaker_ids),
        key=_listing_order,
    )
    return tuple(
        DaySessions(day, tuple(group))
        for day, group in groupby(own, key=lambda session: session.day)
    )


def has_bio(speaker: Speaker) -> bool:
    """Return whether a speaker's bio says anything: a letter or a digit in its text.

    The feed fills a bio nobody wrote with a dash (2026: the five panellists of
    "Beyond the Hype" and two others; 2025: twelve), which an "About" section would
    show as a lone "-".

    Args:
        speaker: The directory speaker.
    """
    return any(char.isalnum() for char in to_text(speaker.bio))


def _listing_order(session: Session) -> tuple[object, ...]:
    """The order a speaker's sessions are listed in: by day, then as the Schedule's."""
    return (session.day, schedule_order(session))


def filter_directory(
    entries: tuple[SpeakerEntry, ...], index: SearchIndex, query: str
) -> tuple[SpeakerEntry, ...]:
    """Return the entries a filter keeps: those whose name holds every word (D-46).

    The matching is search's, over the same folded names (`search(index, query,
    "speakers")`): accents and case ignored, each word anywhere in the name. A filter
    with no word to match keeps every entry and returns `entries` itself: a blank one,
    and one that folds to nothing, such as the lone `’` iOS types before `O’Brien`,
    which search would answer with nothing.

    Args:
        entries: The list's entries (`directory()`).
        index: The search index of the same feed version (`search.search_index`).
        query: What the user typed in the filter field.

    Returns:
        The entries found, in the list's order.
    """
    if not fold(query).split():
        return entries
    found = {speaker.id for speaker in search(index, query, "speakers").speakers}
    return tuple(entry for entry in entries if entry.speaker.id in found)


def letter_groups(entries: Sequence[SpeakerEntry]) -> tuple[LetterGroup, ...]:
    """Return the entries cut into the list's sections, one per letter, in order.

    Args:
        entries: Entries in the list's order (`directory()` or a filtered part of it).

    Returns:
        The groups; equal for equal entries, so an unchanged section compares equal.
    """
    return tuple(
        LetterGroup(letter, tuple(group))
        for letter, group in groupby(entries, key=lambda entry: entry.letter)
    )
