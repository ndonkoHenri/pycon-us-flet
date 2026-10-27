"""Tests for the job listings' placeholders, search text and filter (``core/jobs.py``).

SPON-07, SPON-09, D-278. The roles' rules are ``tests/test_jobs.py``'s, and so are the
helpers both modules use (#623).
"""

from dataclasses import replace

import pytest

from pycon_us.core.jobs import (
    filter_listings,
    is_placeholder,
    listings_of,
)
from pycon_us.core.models import JobListing
from pycon_us.core.sponsors import sponsor_by_slug
from tests.feeds import processed
from tests.test_jobs import DATA, listing, sponsors_of


@pytest.mark.parametrize(
    ("text", "placeholder"),
    [
        ("", True),
        ("  ", True),
        ("-", True),
        ("N/A", True),
        ("n/a.", True),
        ("None", True),
        ("TBD", True),
        ("Careers", False),
        ("Engineer", False),
        ("招聘", False),
    ],
)
def test_a_placeholder_says_nothing(text: str, placeholder: bool) -> None:
    """Blank, a dash, N/A, None and TBD are placeholders; any other word is not."""
    assert is_placeholder(text) == placeholder


def test_a_placeholder_listing_has_no_roles_nor_description() -> None:
    """OpenEDG's ``N/A`` gives no role and no Markdown: nothing to show but the sponsor."""
    openedg = listing("OpenEDG Python Institute")

    assert (openedg.roles, openedg.description_md) == ((), "")
    assert openedg.search_text == "openedg python institute"


@pytest.mark.parametrize(
    "word",
    ["nofollow", "noopener", "avature", "href", "external", "<", "&amp;"],
)
def test_search_text_holds_no_markup(word: str) -> None:
    """No listing's search text matches a tag, an attribute or a link's destination (SPON-07)."""
    assert [j.sponsor_name for j in DATA.job_listings if word in j.search_text] == []


def test_search_text_holds_the_sponsor_the_titles_and_the_text() -> None:
    """A listing matches its sponsor, its role titles, even one from a URL, and its text."""
    assert "anaconda, inc careers" in listing("Anaconda, Inc").search_text
    assert "network testing platforms" in listing("Bloomberg").search_text
    assert "molab" in listing("marimo").search_text
    assert "network ai platform" in listing("NVIDIA").search_text  # the em dash folded


def names(listings: tuple[JobListing, ...]) -> list[str]:
    """The sponsors of ``listings``, in their order."""
    return [job.sponsor_name for job in listings]


def test_the_filter_needs_every_word_in_any_order() -> None:
    """SPON-07: only the listings that hold both words, in feed order."""
    assert names(filter_listings(DATA.job_listings, "senior python")) == [
        "NVIDIA",
        "marimo",
    ]
    assert filter_listings(DATA.job_listings, "python senior") == filter_listings(
        DATA.job_listings, "senior python"
    )
    assert names(filter_listings(DATA.job_listings, "MACHINE learning")) == ["Sentry"]
    assert filter_listings(DATA.job_listings, "rust") == ()


@pytest.mark.parametrize("word", ["nofollow", "href", "noopener"])
def test_the_filter_never_matches_markup(word: str) -> None:
    """Ionic's filter found Bloomberg from ``nofollow`` in its raw HTML; ours nothing."""
    assert "nofollow" in listing("Bloomberg").description  # the markup is there
    assert filter_listings(DATA.job_listings, word) == ()


@pytest.mark.parametrize("query", ["", "   ", "\N{RIGHT SINGLE QUOTATION MARK}"])
def test_a_filter_with_no_word_keeps_the_listings_themselves(query: str) -> None:
    """The same object, so the screen knows no filter applies (no count line)."""
    assert filter_listings(DATA.job_listings, query) is DATA.job_listings


def test_every_2026_listing_is_found_from_its_sponsor() -> None:
    """``listings_of`` finds each listing from its sponsor, once; others have none."""
    found = [job for s in sponsors_of(DATA) for job in listings_of(DATA, s)]

    assert sorted(job.id for job in found) == sorted(j.id for j in DATA.job_listings)
    bloomberg = sponsor_by_slug(DATA, "bloomberg")
    assert bloomberg is not None
    assert listings_of(DATA, bloomberg) == (listing("Bloomberg"),)


def test_a_listing_is_matched_by_the_exact_name() -> None:
    """A name that differs only in case is another sponsor's (SPON-05)."""
    bloomberg = sponsor_by_slug(DATA, "bloomberg")
    assert bloomberg is not None

    assert listings_of(DATA, replace(bloomberg, name="BLOOMBERG")) == ()


def test_2025_has_no_listings_and_processes() -> None:
    """2025's feed has no job listings: every sponsor has none."""
    data = processed(2025)

    assert data.job_listings == ()
    assert all(listings_of(data, s) == () for s in sponsors_of(data))
