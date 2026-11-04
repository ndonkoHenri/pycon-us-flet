"""The year data of the keynotes and panels, and its checks (D-45, SESS-08, SPKR-04).

`content.toml`'s `[[keynotes]]` build into the dataclasses below, through
`year_schema.build()`, as `config.Content.keynotes`: one entry per session, keyed by
the feed's session id, since the feed names a keynote by its speaker and links its
description to the site, and has no photo, role or bio for the people on stage.
`check_keynotes()` checks the entries' own rules when the year loads;
`check_keynote_sessions()` checks their ids against a feed's sessions, each a keynote
or a plenary: the loader's against the year's bundled snapshot when asked
(`config.load_year(check_sessions=True)`), and the
snapshot tool's against a new feed. The callers pass the tracks
(`year_tracks.KEYNOTE_TRACKS`), so this module stays free of the config it builds part
of.
A module of its own, as `year_pages` is, so `config.py` grows by little (D-66).
"""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from pycon_us.core.models import Session
from pycon_us.year_pages import check_https, check_text
from pycon_us.year_schema import YearDataError

KINDS = ("keynote", "panel")
"""What a keynote entry can be: a talk by one or two people, or a panel of several."""


@dataclass(frozen=True)
class KeynoteSpeaker:
    """A person on stage at a keynote or a panel.

    Attributes:
        name: Their name as they write it, in their own capitals.
        role: What they do, in a few words, under the name: "CEO and co-founder,
            Fireworks AI".
        photo_url: Their photo, an `https://` URL; empty for none, when the
            initials stand in.
        bio: A few sentences about them; empty for none.
    """

    name: str
    role: str
    photo_url: str = ""
    bio: str = ""


@dataclass(frozen=True)
class Keynote:
    """What the app adds to one keynote or panel of the feed.

    Attributes:
        session_id: The feed's session id (a slot's `conf_key`, D-42); the loader
            refuses one the year's snapshot does not have.
        kind: `keynote` or `panel` (`KINDS`): a keynote's card shows each
            speaker's photo and bio, a panel's its people as a row of avatars.
        speakers: The people on stage, in the order the site lists them.
        title: The talk's own title, which the feed does not give; empty for none.
        abstract: What the talk or panel is about, in Markdown; empty for none, when
            session detail keeps the feed's description.
    """

    session_id: str
    kind: str
    speakers: tuple[KeynoteSpeaker, ...]
    title: str = ""
    abstract: str = ""


def check_keynotes(keynotes: tuple[Keynote, ...], file: str) -> None:
    """Check the entries' own rules: a known kind, one entry per session, no blank text.

    Args:
        keynotes: The `[[keynotes]]` entries.
        file: The data file they come from, for the messages (`2026/content.toml`).

    Raises:
        YearDataError: A rule is broken; the message names the file and the key.
    """
    seen: set[str] = set()
    for index, keynote in enumerate(keynotes):
        key = f"keynotes[{index}]"
        check_text(keynote.session_id, file, f"{key}.session_id")
        if keynote.session_id in seen:
            raise YearDataError(
                f"{file}: {key}.session_id: duplicate session {keynote.session_id!r}"
            )
        seen.add(keynote.session_id)
        if keynote.kind not in KINDS:
            raise YearDataError(
                f"{file}: {key}.kind: {keynote.kind!r} is not one of {KINDS}"
            )
        if not keynote.speakers:
            raise YearDataError(f"{file}: {key}.speakers: is empty")
        for number, person in enumerate(keynote.speakers):
            where = f"{key}.speakers[{number}]"
            check_text(person.name, file, f"{where}.name")
            check_text(person.role, file, f"{where}.role")
            if person.photo_url:
                check_https(person.photo_url, file, f"{where}.photo_url")


def check_keynote_sessions(
    keynotes: tuple[Keynote, ...],
    sessions: Mapping[str, Session],
    tracks: Collection[str],
    file: str,
) -> None:
    """Refuse a keynote whose session the feed lacks or is no keynote (SESS-08).

    An entry that names no session would enrich nothing and show no card: a typo, or
    a session the feed dropped, which needs a look at the year data. A typo that lands
    on another session would be worse: a talk on the Keynotes page, its speakers
    replaced by the year data's people on its detail. So the session must also be of
    a keynotes' track: the keynotes' own, or the plenaries', which the panels are.

    Args:
        keynotes: The `[[keynotes]]` entries.
        sessions: The feed's sessions, by id.
        tracks: The track keys a keynote or panel can have
            (`year_tracks.KEYNOTE_TRACKS`).
        file: The data file the entries come from, for the message.

    Raises:
        YearDataError: An entry's `session_id` is not among `sessions`, or names
            a session of another track.
    """
    for index, keynote in enumerate(keynotes):
        key = f"{file}: keynotes[{index}].session_id: {keynote.session_id!r}"
        session = sessions.get(keynote.session_id)
        if session is None:
            raise YearDataError(f"{key} is not a session of the year's feed")
        if session.track not in tracks:
            raise YearDataError(
                f"{key} is a {session.track} session, not a keynote or a plenary"
            )


def keynote_of(keynotes: Iterable[Keynote], session_id: str) -> Keynote | None:
    """Return the keynote or panel entry of a session, or None for any other session.

    Args:
        keynotes: The year's entries (`Content.keynotes`).
        session_id: A session id of the feed.
    """
    return next((k for k in keynotes if k.session_id == session_id), None)
