"""Tests for the sponsors by level, `sponsor_by_slug()` and the spotlight pick.

DATA-22, SPON-02 and D-261 for the levels; SHELL-08 and D-298 for the spotlight.

The feed's `conference.sponsors` is an object of sponsor lists keyed by level;
`feed.process()` decodes it through `records.sponsor_levels()` and sorts the levels
once. The invariants over it are in `test_feed_invariants.py`.
"""

import logging
from collections.abc import Callable
from dataclasses import replace
from random import Random
from typing import Any

import pytest

from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Sponsor
from pycon_us.core.sponsors import (
    pick_spotlight,
    sponsor_by_slug,
    spotlight_candidates,
    thanks,
)
from tests.feeds import YEARS, changed, document, processed, settings

type Change = Callable[[dict[str, Any]], object]
"""A change to a feed JSON object, or to one sponsor record of it."""


def sponsors_of(data: ConferenceData) -> list[Sponsor]:
    """Every sponsor of `data`, level by level."""
    return [sponsor for level in data.sponsor_levels for sponsor in level.sponsors]


def sponsors_from(change: Change) -> ConferenceData:
    """The 2026 feed processed with `change` applied to its JSON first."""
    return process(changed(2026, change), settings(2026))


@pytest.mark.parametrize(("year", "levels", "count"), [(2025, 13, 93), (2026, 13, 105)])
def test_every_level_and_sponsor_of_the_feed_is_decoded(
    year: int, levels: int, count: int
) -> None:
    """2025 has 13 levels and 93 sponsors, 2026 13 and 105, none skipped (DATA-22)."""
    data = processed(year)
    assert len(data.sponsor_levels) == levels
    assert len(sponsors_of(data)) == count
    assert data.skipped == ()


@pytest.mark.parametrize("year", YEARS)
def test_levels_come_by_level_order_with_the_feeds_sponsors(year: int) -> None:
    """Each level holds its feed list in feed order, the levels sorted by `level_order`."""
    raw = document(year)["conference"]["sponsors"]
    data = processed(year)
    expected = sorted(raw, key=lambda level: raw[level][0]["level_order"])
    assert [level.name for level in data.sponsor_levels] == expected
    for level in data.sponsor_levels:
        assert level.order == raw[level.name][0]["level_order"]
        assert [s.name for s in level.sponsors] == [r["name"] for r in raw[level.name]]
        assert {s.level for s in level.sponsors} == {level.name}


def test_bloomberg_has_its_booth_table_and_fields() -> None:
    """2026's Bloomberg: Visionary, booth 613, Job Fair table T2, a spotlight candidate."""
    bloomberg = sponsor_by_slug(processed(2026), "bloomberg")
    assert bloomberg is not None
    assert (bloomberg.name, bloomberg.level, bloomberg.level_order) == (
        "Bloomberg",
        "Visionary",
        0,
    )
    assert (bloomberg.booth, bloomberg.job_fair_table) == ("613", "T2")
    assert bloomberg.mobile_banner
    assert bloomberg.logo_url.endswith("/sponsor_web_logos/bloomberg.png")
    assert bloomberg.external_url is None  # the live feed has no website field


def test_a_sponsor_without_booth_or_table_has_none() -> None:
    """NVIDIA has neither a booth nor a table in 2026: both read as None."""
    nvidia = sponsor_by_slug(processed(2026), "nvidia")
    assert nvidia is not None
    assert (nvidia.booth, nvidia.job_fair_table) == (None, None)


@pytest.mark.parametrize("year", YEARS)
def test_mobile_banner_sponsors_are_seven_visionary_six_maintaining_one_sustainability(
    year: int,
) -> None:
    """The 14 spotlight candidates of each year, by level (SHELL-08, SPON-11)."""
    levels = [s.level for s in sponsors_of(processed(year)) if s.mobile_banner]
    expected = {
        2025: {"Visionary": 5, "Sustainability": 1, "Maintaining": 7, "AV Partner": 1},
        2026: {"Visionary": 7, "Sustainability": 1, "Maintaining": 6},
    }[year]
    assert {level: levels.count(level) for level in set(levels)} == expected


def test_sponsor_by_slug_finds_every_2026_sponsor() -> None:
    """Each 2026 sponsor is found by its own slug, as the same object."""
    data = processed(2026)
    for sponsor in sponsors_of(data):
        assert sponsor_by_slug(data, sponsor.slug) is sponsor


@pytest.mark.parametrize(
    "slug", ["", "acme", "Bloomberg", "qube-research-technologies"]
)
def test_sponsor_by_slug_returns_none_for_an_unknown_slug(slug: str) -> None:
    """A slug no sponsor has, in another case or without Ionic's double dash, is None."""
    assert sponsor_by_slug(processed(2026), slug) is None


def test_ionics_double_dash_slug_finds_its_sponsor() -> None:
    """`qube-research--technologies` routes to Qube Research & Technologies (SPON-02)."""
    sponsor = sponsor_by_slug(processed(2026), "qube-research--technologies")
    assert sponsor is not None and sponsor.name == "Qube Research & Technologies"


def test_a_slug_collision_finds_the_first_sponsor_in_level_order() -> None:
    """Two sponsors with one slug: the one in the higher level is found, as in Ionic."""

    def twin(doc: dict[str, Any]) -> None:
        sponsors = doc["conference"]["sponsors"]
        bloomberg = sponsors["Visionary"][2]
        sponsors["Community"].append(dict(bloomberg, name="BLOOMBERG", level_order=12))

    data = sponsors_from(twin)
    found = sponsor_by_slug(data, "bloomberg")
    assert found is not None and (found.name, found.level) == ("Bloomberg", "Visionary")


def test_descriptions_keep_their_line_breaks_as_line_feeds() -> None:
    """A plain description keeps its breaks; the feed's CR LF become line feeds."""
    devitjobs = sponsor_by_slug(processed(2026), "devitjobs")
    assert devitjobs is not None
    assert devitjobs.description.startswith(
        "DevITJobs is a job portal built by engineers for engineers.\n\n"
        "What sets us apart?\n\n"
    )
    assert "\r" not in "".join(s.description for s in sponsors_of(processed(2026)))


def test_html_in_a_description_stays_as_text() -> None:
    """A description is plain text: markup in one is kept as written, not converted."""

    def tag(doc: dict[str, Any]) -> None:
        doc["conference"]["sponsors"]["Visionary"][0]["description"] = "<b>Fast</b>"

    (first, *_) = sponsors_of(sponsors_from(tag))
    assert first.description == "<b>Fast</b>"


def test_a_feed_without_sponsors_has_no_levels() -> None:
    """A feed without `conference.sponsors`, or without `conference`, processes."""

    def no_sponsors(doc: dict[str, Any]) -> None:
        del doc["conference"]["sponsors"]

    def no_conference(doc: dict[str, Any]) -> None:
        del doc["conference"]

    for change in (no_sponsors, no_conference):
        data = sponsors_from(change)
        assert (data.sponsor_levels, data.skipped) == ((), ())
        assert len(data.sessions) == len(processed(2026).sessions)


def test_a_malformed_sponsor_is_skipped_and_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A sponsor that cannot be read is skipped, by level and index; the rest are kept."""

    def spoil(doc: dict[str, Any]) -> None:
        doc["conference"]["sponsors"]["Visionary"][2]["level_order"] = "0"

    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = sponsors_from(spoil)
    reason = (
        "conference.sponsors['Visionary'][2]: "
        "'level_order' should be an integer, got '0'"
    )
    assert data.skipped == (reason,)
    assert [r.getMessage() for r in caplog.records] == [
        f"Skipped a feed record: {reason}"
    ]
    assert len(sponsors_of(data)) == 104
    assert len(data.sponsor_levels[0].sponsors) == 6


@pytest.mark.parametrize(
    ("spoil", "problem"),
    [
        (lambda s: s.update(name=None), "'name' should be a string, got None"),
        (lambda s: s.update(name="日本"), "'name' has no letter or digit"),
        (lambda s: s.update(name="  "), "'name' has no letter or digit"),
        (lambda s: s.update(name=" & "), "'name' has no letter or digit"),
        (lambda s: s.update(mobile_banner="yes"), "'mobile_banner' should be true"),
        (lambda s: s.update(booth_number=["613"]), "'booth_number' should be a string"),
        (lambda s: s.update(description=7), "'description' should be a string"),
        (lambda s: s.update(external_url=1), "'external_url' should be a string"),
        (lambda s: s.pop("level_order"), "'level_order' should be an integer"),
        (lambda s: s.update(level_order=True), "'level_order' should be an integer"),
    ],
)
def test_each_bad_field_skips_its_sponsor(spoil: Change, problem: str) -> None:
    """Each malformed field skips only its sponsor, naming the field."""

    def change(doc: dict[str, Any]) -> None:
        spoil(doc["conference"]["sponsors"]["Community"][0])

    data = sponsors_from(change)
    (reason,) = data.skipped
    assert reason.startswith("conference.sponsors['Community'][0]: ")
    assert problem in reason
    assert len(sponsors_of(data)) == 104


def test_tolerated_fields_read_as_their_defaults() -> None:
    """A null banner is False, numbers and padded text are booths, blanks are None."""

    def loosen(doc: dict[str, Any]) -> None:
        first, second, third = doc["conference"]["sponsors"]["Visionary"][:3]
        first.update(mobile_banner=None, booth_number=613, external_url="")
        second.update(booth_number="  ", job_fair_table_number=" T4 ")
        for key in ("logo_url", "description", "mobile_banner", "booth_number"):
            third.pop(key)
        third["external_url"] = "https://example.com"

    first, second, third, *_ = sponsors_of(sponsors_from(loosen))
    assert (first.mobile_banner, first.booth, first.external_url) == (
        False,
        "613",
        None,
    )
    assert (second.booth, second.job_fair_table) == (None, "T4")
    assert (third.logo_url, third.description, third.mobile_banner, third.booth) == (
        "",
        "",
        False,
        None,
    )
    assert third.external_url == "https://example.com"


def test_a_level_that_is_not_a_list_is_skipped() -> None:
    """A level whose value is not a list is skipped whole; the other levels stay."""

    def spoil(doc: dict[str, Any]) -> None:
        doc["conference"]["sponsors"]["Media"] = {"name": "Oops"}

    data = sponsors_from(spoil)
    assert data.skipped == (
        "conference.sponsors['Media']: should be a list, got {'name': 'Oops'}",
    )
    assert "Media" not in [level.name for level in data.sponsor_levels]
    assert len(data.sponsor_levels) == 12


def test_a_level_left_without_sponsors_is_not_listed() -> None:
    """An empty level, or one whose every sponsor is skipped, gives no level."""

    def spoil(doc: dict[str, Any]) -> None:
        sponsors = doc["conference"]["sponsors"]
        sponsors["Empty"] = []
        sponsors["Sustainability"][0]["name"] = 1

    data = sponsors_from(spoil)
    names = [level.name for level in data.sponsor_levels]
    assert "Empty" not in names and "Sustainability" not in names
    assert len(names) == 12
    assert data.skipped[0].startswith("conference.sponsors['Sustainability'][0]: ")


def test_sponsors_that_are_not_an_object_are_skipped_whole() -> None:
    """A `conference.sponsors` list is skipped, named; the schedule still processes."""

    def spoil(doc: dict[str, Any]) -> None:
        doc["conference"]["sponsors"] = []

    data = sponsors_from(spoil)
    assert data.sponsor_levels == ()
    assert data.skipped == ("conference.sponsors: should be an object, got []",)
    assert len(data.sessions) == len(processed(2026).sessions)


def test_levels_with_one_order_keep_feed_order() -> None:
    """Two levels with the same `level_order` stay in the feed's order."""

    def tie(doc: dict[str, Any]) -> None:
        sponsors = doc["conference"]["sponsors"]
        for sponsor in sponsors["Media"]:
            sponsor["level_order"] = 0

    names = [level.name for level in sponsors_from(tie).sponsor_levels]
    assert names[:3] == ["Visionary", "Media", "Sustainability"]


# ------------------------------------------------------------------ the spotlight


def test_spotlight_candidates_are_the_banner_sponsors_in_level_order() -> None:
    """The candidates are the 14 `mobile_banner` sponsors of 2026, top level first."""
    data = processed(2026)
    candidates = spotlight_candidates(data)
    assert [s for s in sponsors_of(data) if s.mobile_banner] == list(candidates)
    assert len(candidates) == 14
    assert candidates[0].slug == "nvidia"


def test_the_pick_is_a_candidate_and_follows_the_seed() -> None:
    """A seeded `Random` picks a candidate, the same one for the same seed."""
    candidates = spotlight_candidates(processed(2026))
    for seed in range(20):
        first = pick_spotlight(candidates, "", Random(seed))
        assert first in candidates
        assert pick_spotlight(candidates, "", Random(seed)) is first


def test_the_pick_keeps_the_current_sponsor_while_it_is_a_candidate() -> None:
    """The slug picked before wins: nothing is drawn while it is still a candidate."""
    candidates = spotlight_candidates(processed(2026))
    rng = Random(1)
    state = rng.getstate()
    kept = pick_spotlight(candidates, "microsoft", rng)
    assert kept is not None and kept.slug == "microsoft"
    assert rng.getstate() == state  # no draw


def test_the_pick_draws_again_when_the_sponsor_leaves() -> None:
    """A slug that is no longer a candidate (dropped, or its banner off) is replaced."""
    candidates = spotlight_candidates(processed(2026))
    picked = pick_spotlight(candidates, "bloomberg-gone", Random(3))
    assert picked in candidates


def test_without_candidates_nothing_is_picked() -> None:
    """No banner sponsor, no spotlight, whatever was picked before."""
    assert pick_spotlight((), "nvidia", Random(0)) is None


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("Visionary", "Thanks to NVIDIA, a Visionary sponsor"),
        ("Associate", "Thanks to NVIDIA, an Associate sponsor"),
    ],
)
def test_the_thanks_takes_an_before_a_vowel(level: str, expected: str) -> None:
    """The article goes by the level's first letter: "an Associate sponsor"."""
    nvidia = spotlight_candidates(processed(2026))[0]
    assert thanks(replace(nvidia, level=level)) == expected
