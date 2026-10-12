"""Tests for the markup conversion at the end of feed processing (D-130, D-140; DATA-23..25).

``feed.process()`` converts every HTML field once, after Ionic's rules, and keeps the raw
HTML beside the Markdown. The converter itself is tested in ``test_html_md.py`` and on
the feeds' values in ``test_html_md_feeds.py`` (which also checks that no tag is left
outside code); these tests check the wiring, on the recorded 2025 and 2026 feeds.
"""

import logging
import re
from types import SimpleNamespace
from typing import Any

import pytest

from pycon_us.core import html_md
from pycon_us.core.feed import FeedError, process
from pycon_us.core.html_md import to_markdown, to_text
from pycon_us.core.queries import fold
from tests.feeds import YEARS, changed, document, processed, settings

TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def site_url(year: int) -> str:
    return settings(year).site_url


@pytest.mark.parametrize("year", YEARS)
def test_session_descriptions_are_markdown_beside_the_raw_html(year: int) -> None:
    data = processed(year)
    sessions = [s for s in data.sessions.values() if s.kind != "open-space"]
    assert any(TAG.search(s.description) for s in sessions)
    for session in sessions:
        assert session.description_md == to_markdown(
            session.description, site_url(year)
        )


@pytest.mark.parametrize("year", YEARS)
def test_open_space_descriptions_pass_through_as_markdown(year: int) -> None:
    """DATA-25: they are Markdown already, so converting them would escape it (D-115)."""
    spaces = [s for s in processed(year).sessions.values() if s.kind == "open-space"]
    assert spaces
    for space in spaces:
        assert space.description_md == space.description


@pytest.mark.parametrize("year", YEARS)
def test_speaker_bios_are_markdown(year: int) -> None:
    speakers = processed(year).speakers.values()
    assert any(TAG.search(s.bio) for s in speakers)
    for speaker in speakers:
        assert speaker.bio_md == to_markdown(speaker.bio, site_url(year))


@pytest.mark.parametrize("year", YEARS)
def test_poster_descriptions_are_markdown(year: int) -> None:
    data = processed(year)
    assert data.posters  # 2025's are nested in its poster slot (D-121)
    for poster in data.posters:
        assert poster.description_md == to_markdown(poster.description, site_url(year))
        detail = data.sessions[f"poster-detail-{poster.id}"]
        assert detail.description_md == poster.description_md


@pytest.mark.parametrize("year", YEARS)
def test_sprint_and_job_descriptions_are_markdown(year: int) -> None:
    data = processed(year)
    assert len(data.sprints) == len(document(year).get("sprints", []))
    assert len(data.job_listings) == len(document(year).get("job-listings", []))
    for item in (*data.sprints, *data.job_listings):
        assert item.description_md == to_markdown(item.description, site_url(year))


def test_plain_text_sprint_descriptions_keep_their_paragraphs() -> None:
    """D-114: 15 of the 24 2026 sprint descriptions have no tag; Ionic lost their breaks."""
    plain = [s for s in processed(2026).sprints if not TAG.search(s.description)]
    assert len(plain) == 15
    assert any("\n\n" in s.description_md for s in plain)


@pytest.mark.parametrize("year", YEARS)
def test_content_blocks_are_kept_raw_and_as_markdown(year: int) -> None:
    data = processed(year)
    content = document(year)["conference"]["content"]
    assert dict(data.content) == content
    assert data.content_md.keys() == content.keys()
    for key, value in content.items():
        assert data.content_md[key] == to_markdown(value, site_url(year))


def test_content_block_links_are_markdown_links() -> None:
    about_psf = processed(2026).content_md["about-psf"]
    assert "- [PSF home page](https://www.python.org/psf-landing/)" in about_psf


@pytest.mark.parametrize("year", YEARS)
def test_search_text_is_the_folded_name_description_text_and_speakers(
    year: int,
) -> None:
    """D-46: search matches text, never markup, ignoring case and accents."""
    sessions = processed(year).sessions.values()
    for session in (s for s in sessions if s.kind != "open-space"):
        parts = [session.name, to_text(session.description), *session.speaker_names]
        assert session.search_text == fold(" ".join(parts))


@pytest.mark.parametrize("year", YEARS)
def test_open_space_search_text_has_no_markdown_markup(year: int) -> None:
    """D-46, D-140: an open space's Markdown links and markers are not searched."""
    spaces = [s for s in processed(year).sessions.values() if s.kind == "open-space"]
    assert any("](" in s.description for s in spaces)
    for space in spaces:
        assert space.search_text.startswith(fold(space.name))
        for markup in ("](", "*", "`"):
            assert markup not in space.search_text


def test_open_space_search_text_keeps_link_text_without_destinations() -> None:
    """2026's pytest open space links ``[pytest](pytest.org)`` and bolds a phrase."""
    session = processed(2026).sessions["9086"]
    assert "[pytest](pytest.org) is great" in session.description
    assert "pytest is great" in session.search_text
    assert "large system test suite" in session.search_text
    assert "pytest.org" not in session.search_text
    assert "github.com" not in session.search_text


def test_open_space_search_text_keeps_underscores_in_identifiers() -> None:
    session = processed(2025).sessions["9099"]
    assert "ic_ocr_cataloger" in session.search_text


def test_search_text_ignores_accents_and_case() -> None:
    def accent(doc: dict[str, Any]) -> None:
        slot = next(s for s in doc["schedule"] if s["kind"] == "talk")
        slot.update(name="Cristián's TALK", description="<p>Über <b>Python</b></p>")

    data = process(changed(2026, accent), settings(2026))
    (session,) = [s for s in data.sessions.values() if s.name == "Cristián's TALK"]
    assert session.search_text.startswith("cristian's talk uber python ")


def test_the_rules_read_the_raw_description() -> None:
    """Rule 16 runs last: Ionic's placeholder rule sees ``<p></p>`` as a description."""

    def empty_paragraph(doc: dict[str, Any]) -> None:
        slot = next(s for s in doc["schedule"] if str(s["conf_key"]) == "130")
        slot["description"] = "<p></p>"

    data = process(changed(2026, empty_paragraph), settings(2026))
    assert "130" not in data.dropped["placeholder"]
    assert data.sessions["130"].description == "<p></p>"
    assert data.sessions["130"].description_md == ""


def test_each_distinct_value_converts_once(monkeypatch: pytest.MonkeyPatch) -> None:
    converted: list[str] = []

    def counting(value: str, site_url: str) -> str:
        converted.append(value)
        return to_markdown(value, site_url)

    monkeypatch.setattr(html_md, "to_markdown", counting)
    data = processed(2026)
    assert len(converted) == len(set(converted))
    assert (
        data.posters[0].description in converted
    )  # once for the poster and its detail


def test_conversion_time_counts_in_the_processing_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """D-109 and D-130: ``Feed processed in N ms`` includes the conversion."""
    clock = SimpleNamespace(now=0.0)

    def slow(value: str, site_url: str) -> str:
        clock.now += 1.0  # each conversion takes a second of the fake clock
        return to_markdown(value, site_url)

    monkeypatch.setattr(
        "pycon_us.core.feed.time", SimpleNamespace(perf_counter=lambda: clock.now)
    )
    monkeypatch.setattr(html_md, "to_markdown", slow)
    with caplog.at_level(logging.INFO, logger="pycon_us.core.feed"):
        processed(2026)
    milliseconds = int(re.findall(r"Feed processed in (\d+) ms", caplog.text)[0])
    assert milliseconds == round(clock.now * 1000) > 0


def test_a_content_block_that_is_not_text_is_skipped() -> None:
    def spoil(doc: dict[str, Any]) -> None:
        doc["conference"]["content"]["wifi"] = ["not", "text"]

    data = process(changed(2026, spoil), settings(2026))
    assert data.skipped == (
        "conference.content['wifi']: should be a string, got ['not', 'text']",
    )
    assert "wifi" not in data.content and "wifi" not in data.content_md
    assert "about" in data.content_md


def test_a_feed_without_content_has_none() -> None:
    data = process(changed(2026, lambda doc: doc.pop("conference")), settings(2026))
    assert data.content == {} and data.content_md == {}
    assert data.skipped == ()


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda doc: doc.update(conference=[]), "'conference' is not an object"),
        (
            lambda doc: doc["conference"].update(content="<p>About</p>"),
            "'conference.content' is not an object",
        ),
    ],
)
def test_conference_content_of_the_wrong_type_raises_feed_error(
    change: Any, problem: str
) -> None:
    with pytest.raises(FeedError, match=problem):
        process(changed(2026, change), settings(2026))
