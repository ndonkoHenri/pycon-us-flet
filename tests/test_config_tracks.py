"""Tests for the year data's tracks: their names, icons, slugs and pages (D-45)."""

import flet as ft
import pytest

from pycon_us import config
from pycon_us.config import load_year
from pycon_us.year_tracks import TRACK_GROUPS

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


def test_track_name_is_the_short_name_and_the_plural_stays_on_the_track() -> None:
    """``track_name`` says "AI"; the AI track itself holds the title of its list."""
    conference = load_year(2026).conference
    assert conference.track_name("Ai") == "AI"
    assert conference.track("Ai").plural == "Future of AI with Python"


def test_security_keeps_its_track_title() -> None:
    """Security's short name is its key and its plural is its track's title."""
    conference = load_year(2026).conference
    assert conference.track_name("Security") == "Security"
    assert conference.track("Security").plural == "Trailblazing Python Security"


def test_2026_registry_names_every_processed_track() -> None:
    """2026's track registry holds exactly the fifteen tracks of its processed feed."""
    keys = {track.key for track in load_year(2026).conference.tracks}
    assert keys == {
        "Talk",
        "Keynote",
        "Plenary",
        "Lightning-talks",
        "Ai",
        "Security",
        "Charla",
        "Poster",
        "Tutorial",
        "Sponsor Presentation",
        "Open Space",
        "Summit",
        "Event",
        "Informational",
        "Break",
    }


def test_track_name_is_not_the_key() -> None:
    """``track_name`` gives the display name "Lightning talks", not the key."""
    assert load_year(2026).conference.track_name("Lightning-talks") == "Lightning talks"


def test_unknown_track_falls_back_to_its_humanised_key() -> None:
    """A track the registry lacks is named by its humanised key, in a known group."""
    conference = load_year(2026).conference
    assert conference.track_name("Hallway-track") == "Hallway track"
    assert conference.track("Hallway-track").plural == "Hallway track"
    assert conference.track("Hallway-track").group in TRACK_GROUPS


@pytest.mark.parametrize("year", YEARS)
def test_track_icons_are_material_icon_names(year: int) -> None:
    """Every track's icon names one of Flet's Material icons."""
    for track in load_year(year).conference.tracks:
        assert hasattr(ft.Icons, track.icon), track.key


@pytest.mark.parametrize("year", YEARS)
def test_every_track_has_an_icon_of_its_own(year: int) -> None:
    """No two tracks of a year share an icon.

    The hub shows the icons side by side as the key to the tracks (D-199): two rows told
    apart by their circle's colour alone would break D-33.
    """
    icons = [track.icon for track in load_year(year).conference.tracks]
    assert len(icons) == len(set(icons)), sorted(icons)


def test_track_pages_have_clean_explicit_slugs() -> None:
    """DATA-29: written in the year data, never Ionic's derived ``ais`` or ``…talkss``."""
    slugs = {t.key: t.slug for t in load_year(2026).conference.tracks}
    assert slugs == {
        "Talk": "talks",
        "Keynote": "keynotes",
        "Plenary": "plenaries",
        "Lightning-talks": "lightning-talks",
        "Ai": "ai",
        "Security": "security",
        "Charla": "charlas",
        "Poster": "posters",
        "Tutorial": "tutorials",
        "Sponsor Presentation": "sponsor-presentations",
        "Open Space": "open-spaces",
        "Summit": "summits",
        "Event": "events",
        "Informational": "notices",
        "Break": "breaks",
    }


@pytest.mark.parametrize("year", YEARS)
def test_every_track_has_a_slug_and_a_legend_line(year: int) -> None:
    """Every track has a slug of its own in its year, and a legend that is not blank."""
    tracks = load_year(year).conference.tracks
    assert len({t.slug for t in tracks}) == len(tracks)
    assert all(t.legend.strip() for t in tracks)


def test_a_slug_finds_its_track_and_an_unknown_one_none() -> None:
    """The slug "charlas" finds the Charla track; Ionic's or unknown slugs find none.

    A slug is matched as written: "Charlas" and the empty slug find no track either.
    """
    conference = load_year(2026).conference
    track = conference.track_for_slug("charlas")
    assert track is not None and track.key == "Charla"
    for slug in ("ais", "lightning-talkss", "Charlas", "", "python"):
        assert conference.track_for_slug(slug) is None, slug


def test_a_track_the_registry_lacks_has_no_page() -> None:
    """A track the registry lacks has an empty slug, which finds no track."""
    conference = load_year(2026).conference
    assert conference.track("Hallway-track").slug == ""
    assert conference.track_for_slug("") is None


def test_ai_and_security_are_the_new_tracks_of_2026() -> None:
    """SCHED-21: Ionic's "New track!" badge, now a fact of the year data."""
    assert {t.key for t in load_year(2026).conference.tracks if t.new} == {
        "Ai",
        "Security",
    }
    assert not any(t.new for t in load_year(2025).conference.tracks)
