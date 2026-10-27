"""Tests for the days query, the fold and the Speakers order (architecture §7.5).

DATA-17's days, and the fold and Speakers order of D-46 and D-180. The schedule queries
are tested in ``test_timeline.py``, Now's and My schedule's in ``test_agenda.py`` and
its parts.
"""

import unicodedata
from datetime import date
from typing import Any

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.models import Speaker
from pycon_us.core.queries import days, fold, speaker_order
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


def test_2026_days_run_from_tutorials_to_the_last_sprint_day() -> None:
    """DATA-17: the two sprint days have no sessions in the feed but get a day."""
    conference = load_year(2026).conference
    assert days(processed(2026), conference.first_day, conference.last_day) == tuple(
        date(2026, 5, d) for d in range(13, 20)
    )


@pytest.mark.parametrize("year", YEARS)
def test_every_schedule_day_is_one_of_the_days(year: int) -> None:
    """The days run first to last day, sorted, and hold every schedule day."""
    conference = load_year(year).conference
    result = days(processed(year), conference.first_day, conference.last_day)
    assert {day.date for day in processed(year).days} <= set(result)
    assert list(result) == sorted(set(result))
    assert (result[0], result[-1]) == (conference.first_day, conference.last_day)


def test_a_session_outside_the_conference_dates_widens_the_days() -> None:
    """A session two days early adds its day, and the day between, to the days."""

    def early(doc: dict[str, Any]) -> None:
        doc["schedule"][5].update(
            start="2026-05-11T09:00:00-07:00", end="2026-05-11T10:00:00-07:00"
        )

    data = process(changed(2026, early), settings(2026))
    conference = load_year(2026).conference
    result = days(data, conference.first_day, conference.last_day)
    assert result[:3] == (date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13))


@hypothesis_settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.text())
def test_fold_is_stable_and_leaves_no_marks(text: str) -> None:
    """D-180: folding a folded text changes nothing, so a query and the index agree."""
    folded = fold(text)
    assert fold(folded) == folded
    assert not any(unicodedata.category(c) in ("Mn", "Me", "Cf") for c in folded)


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("Cristián", "cristian"),
        ("ÜBER Python", "uber python"),
        ("Straße", "strasse"),  # case folding, not just lower-casing
        ("ẞ", "ss"),  # the capital sharp s
        ("ﬁle ﬂow", "file flow"),  # NFKD splits the ligatures
        ("ＰＹＴＨＯＮ ①", "python 1"),  # full-width and circled forms
        ("İstanbul", "istanbul"),  # İ decomposes to I and a dot above
        ("ıi", "ii"),  # dotless i
        ("Łukasz Paweł Żal", "lukasz pawel zal"),  # 2025 speakers; ł does not decompose
        ("Søren Ærø Œuvre", "soren aero oeuvre"),
        ("Đorđe", "dorde"),
        ("don’t ‘quote’", "dont quote"),  # iOS types the curly forms
        ("don't O’Reilly", "dont oreilly"),  # apostrophes go: "dont" finds both
        ("don´t", "dont"),  # an acute accent typed as one would split the word
        ("Hawaiʻi Oʼahu", "hawaii oahu"),  # modifier letters used as apostrophes
        ("“Hello” „world‟", '"hello" "world"'),
        ("type‐safe – fast — done ‒ 1−2 ―", "type-safe - fast - done - 1-2 -"),
        ("non‑breaking", "non-breaking"),  # NFKD makes it a hyphen, then ASCII
        ("soft\u00adhyphen zero\u200bwidth", "softhyphen zerowidth"),  # invisible
        ("\u202eevil\u202c", "evil"),  # bidi controls (2025 has both)
        ("a\u00a0b", "a b"),  # a no-break space is a space
        ("Ñandú", "nandu"),
        ("ΆΘΗΝΑ", "αθηνα"),  # not only Latin
    ],
)
def test_fold_ignores_case_accents_and_typography(text: str, folded: str) -> None:
    """D-46, D-180: search and the Speakers sort compare folded text."""
    assert fold(text) == folded


def test_speakers_sort_by_folded_name_then_id() -> None:
    """D-46: the Speakers list and search share one order; equal names keep theirs."""
    speakers = [
        Speaker("9", "carla", "", ""),
        Speaker("2", "Álvaro", "", ""),
        Speaker("8", "O’Brien", "", ""),
        Speaker("1", "ALVARO", "", ""),
        Speaker("3", "Ofelia", "", ""),
    ]
    assert [s.id for s in sorted(speakers, key=speaker_order)] == [
        "1",  # alvaro, 1
        "2",  # alvaro, 2
        "9",  # carla
        "8",  # obrien: the apostrophe does not count
        "3",  # ofelia
    ]
