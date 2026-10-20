"""The reviewed snapshot's view of a processed feed: ``outline()`` (D-77, D-261).

``tests/test_feed_invariants.py`` compares it with
``tests/fixtures/snapshots/outline-<year>.json``, and the stable-ids invariant of
``tools/feed_invariants.py`` compares two of them; a full ``dataclasses.asdict`` dump
would be too large to review (testing-and-quality.md §3.3). It moved here from
``feed_invariants.py`` when that module passed D-66's ~400 lines.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from pycon_us.core.models import ConferenceData, Session, Sponsor


def outline(data: ConferenceData, zone: ZoneInfo) -> dict[str, object]:
    """A compact, reviewable view of the model: one line per session.

    A line reads ``id | name | track | shown location | start-end`` in conference time,
    then, when they apply: ``shown HH:MM``, ``pre-registration``, ``español``,
    ``speakers <ids>`` and ``text <names not in the directory>``. ``markdown`` shows
    the converted fields (D-130): see ``markdown_samples``. ``sponsors`` lists each
    level in order, one line per sponsor: see ``sponsor_line``.
    """

    def line(session: Session) -> str:
        parts = [
            session.id,
            session.name,
            session.track,
            session.display_location or "-",
            f"{clock(session.start, zone)}-{clock(session.end, zone)}",
        ]
        if session.display_start != session.start:
            parts.append(f"shown {clock(session.display_start, zone)}")
        if session.pre_registered:
            parts.append("pre-registration")
        if session.spanish:
            parts.append("español")
        if session.speaker_ids:
            parts.append("speakers " + " ".join(session.speaker_ids))
        linked = {data.speakers[i].name for i in session.speaker_ids}
        if text := [name for name in session.speaker_names if name not in linked]:
            parts.append("text " + "; ".join(text))
        return " | ".join(parts)

    return {
        "days": {
            day.date.isoformat(): {
                clock(group.start, zone): [
                    line(data.sessions[i]) for i in group.session_ids
                ]
                for group in day.groups
            }
            for day in data.days
        },
        "outside the timeline": [
            line(s) for s in data.sessions.values() if not s.in_timeline
        ],
        "rooms": [
            f"{room.slug}: {room.name} ({len(room.session_ids)})"
            for room in data.rooms.values()
        ],
        "speakers": [f"{s.id}: {s.name}" for s in data.speakers.values()],
        "dropped": {rule: len(ids) for rule, ids in data.dropped.items()},
        "skipped": list(data.skipped),
        "markdown": markdown_samples(data),
        # A list of one-key objects: the snapshot sorts an object's keys, not a list.
        "sponsors": [
            {f"{level.name} ({level.order})": [sponsor_line(s) for s in level.sponsors]}
            for level in data.sponsor_levels
        ],
    }


def sponsor_line(sponsor: Sponsor) -> str:
    """One sponsor as ``slug | name``, then what applies (DATA-22).

    ``booth <booth>``, ``table <table>``, ``banner`` (a spotlight candidate) and
    ``website <url>``. Logos and descriptions are left out: too long to review.
    """
    parts = [sponsor.slug, sponsor.name]
    if sponsor.booth:
        parts.append(f"booth {sponsor.booth}")
    if sponsor.job_fair_table:
        parts.append(f"table {sponsor.job_fair_table}")
    if sponsor.mobile_banner:
        parts.append("banner")
    if sponsor.external_url:
        parts.append(f"website {sponsor.external_url}")
    return " | ".join(parts)


def markdown_samples(data: ConferenceData) -> dict[str, list[str]]:
    """Every content block's Markdown, and one of each other converted field, by line.

    The other fields show their first value that conversion changed: enough to review a
    change of conversion without copying every description into the snapshot. Open
    spaces pass through unchanged (DATA-25), so none is shown.
    """
    samples = {
        f"content {key}": value.splitlines() for key, value in data.content_md.items()
    }
    fields = {
        "session": [
            (s.id, s.description, s.description_md) for s in data.sessions.values()
        ],
        "speaker": [(s.id, s.bio, s.bio_md) for s in data.speakers.values()],
        "poster": [(p.id, p.description, p.description_md) for p in data.posters],
        "sprint": [(s.id, s.description, s.description_md) for s in data.sprints],
        "job listing": [
            (j.id, j.description, j.description_md) for j in data.job_listings
        ],
    }
    for field, values in fields.items():
        if sample := next((v for v in values if v[1] != v[2]), None):
            samples[f"{field} {sample[0]}"] = sample[2].splitlines()
    return samples


def clock(moment: datetime, zone: ZoneInfo) -> str:
    """The time of ``moment`` in ``zone``, as ``HH:MM``."""
    return moment.astimezone(zone).strftime("%H:%M")
