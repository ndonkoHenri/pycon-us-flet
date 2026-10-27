"""Tests for the job listings' roles and sponsors (``core/jobs.py``).

SPON-05, DATA-24, D-278. ``parse_roles()`` runs on every 2026 listing (2025's feed has
none) and on small listings written here, one rule each: anchors, bare URLs and their
titles, long-form listings, and which links a role keeps. Placeholders, the search text
and the filter are ``test_jobs_search.py``'s, which imports this module's helpers
(#623).
"""

from dataclasses import replace
from html import unescape

import pytest

from pycon_us.config import load_year
from pycon_us.core.html_md import to_text
from pycon_us.core.jobs import (
    parse_roles,
    read_listing,
)
from pycon_us.core.models import ConferenceData, JobListing, Role, Sponsor
from tests.feeds import processed

SITE = load_year(2026).conference.site_url
DATA = processed(2026)


def listing(sponsor: str) -> JobListing:
    """The 2026 job listing of ``sponsor``, by its exact name."""
    return next(job for job in DATA.job_listings if job.sponsor_name == sponsor)


def sponsors_of(data: ConferenceData) -> list[Sponsor]:
    """Every sponsor of ``data``, level by level."""
    return [sponsor for level in data.sponsor_levels for sponsor in level.sponsors]


LISTINGS = [
    # sponsor, roles, the roles' titles come from their URLs, a description shows
    ("Bloomberg", 15, False, True),
    ("Temporal", 9, False, True),
    ("Hudson River Trading", 5, False, True),
    ("Sentry", 5, False, True),
    ("NVIDIA", 2, False, True),
    ("Old Mission", 1, False, True),
    ("Tower Research Capital", 1, False, True),
    ("Anaconda, Inc", 1, True, True),
    ("Capital One", 1, True, True),
    ("Qube Research & Technologies", 1, True, True),
    ("SerpApi", 0, False, True),
    ("marimo", 0, False, True),
    ("OpenEDG Python Institute", 0, False, False),
]
"""Every 2026 listing: how many roles it links, how they are titled, and its text."""


def test_the_table_covers_every_2026_listing() -> None:
    """``LISTINGS`` names each of the 13 listings of 2026 once."""
    assert sorted(row[0] for row in LISTINGS) == sorted(
        job.sponsor_name for job in DATA.job_listings
    )


@pytest.mark.parametrize(("sponsor", "count", "from_url", "described"), LISTINGS)
def test_every_2026_listing_gets_its_roles(
    sponsor: str, count: int, from_url: bool, described: bool
) -> None:
    """Each 2026 listing links its roles, titled by its own text where it has one.

    Anchors and ``Title | URL`` items keep their text; a careers page alone in a
    paragraph is titled from its URL. Every link is one the listing wrote. Long-form
    listings have no roles and show their Markdown; OpenEDG's ``N/A`` has neither.
    """
    job = listing(sponsor)
    text = to_text(job.description)

    assert len(job.roles) == count
    assert all(role.url in unescape(job.description) for role in job.roles)
    assert {role.title in text for role in job.roles} <= {not from_url}
    assert bool(job.description_md) == described


def test_careers_pages_are_titled_from_their_urls() -> None:
    """Anaconda, Capital One and Qube give only a URL: its last segment, readable, titles it."""
    assert [
        listing(name).roles
        for name in ("Anaconda, Inc", "Capital One", "Qube Research & Technologies")
    ] == [
        (Role("Careers", "https://www.anaconda.com/about-us/careers"),),
        (Role("Python jobs", "https://www.capitalonecareers.com/python-jobs"),),
        (Role("Careers", "https://www.qube-rt.com/careers/"),),
    ]


def test_title_bar_url_items_are_titled_by_the_text_before_the_url() -> None:
    """Hudson River Trading's ``Title | URL`` items lose the bar, not the title's dash."""
    roles = listing("Hudson River Trading").roles

    assert roles[0] == Role(
        "Research Engineer",
        "https://www.hudsonrivertrading.com/hrt-job/experienced-research-engineer/",
    )
    assert roles[2].title == "Software Engineer - AI Tools"


def test_anchors_keep_their_text_and_decoded_links() -> None:
    """Bloomberg's anchors are titled by their text, entities decoded, in feed order."""
    roles = listing("Bloomberg").roles

    assert roles[0] == Role(
        "Trade Automation & Execution, New York",
        "https://bloomberg.avature.net/su/513de60ccd35aae5",
    )
    assert roles[-1].title == "Data Gateway Interfaces, Princeton NJ"
    assert "&amp;" not in listing("NVIDIA").roles[0].url


def test_every_2026_role_links_an_absolute_https_page() -> None:
    """Every role of 2026 opens an absolute ``https`` address."""
    urls = [role.url for job in DATA.job_listings for role in job.roles]

    assert len(urls) == 41
    assert all(url.startswith("https://") for url in urls)


@pytest.mark.parametrize(
    ("href", "url"),
    [
        ("https://example.org/jobs/1", "https://example.org/jobs/1"),
        ("HTTP://example.org/jobs/1", "HTTP://example.org/jobs/1"),
        ("/2026/sponsors/jobs/", "https://us.pycon.org/2026/sponsors/jobs/"),
        ("//jobs.example.org/1", "https://jobs.example.org/1"),
        ("jobs.example.org/1", "https://jobs.example.org/1"),
    ],
)
def test_an_anchors_link_is_joined_as_feed_link_joins_it(href: str, url: str) -> None:
    """A role's link is absolute: a site path joins the site, a scheme-less host gets https."""
    html = f'<ul><li><a href="{href}">Engineer</a></li></ul>'

    assert parse_roles(html, SITE) == (Role("Engineer", url),)


@pytest.mark.parametrize(
    "href",
    [
        "mailto:jobs@example.org",
        "javascript:alert(1)",
        "tel:+1-555-0100",
        "ftp://example.org/jobs",
        "#apply",
        "../jobs",
        "",
        "http://[",
    ],
)
def test_an_anchor_that_opens_no_web_page_is_no_role(href: str) -> None:
    """Only ``http`` and ``https`` links are roles: other schemes and page-relative links go."""
    html = f'<p><a href="{href}">Engineer</a></p>'

    assert parse_roles(html, SITE) == ()


def test_an_anchor_without_href_is_no_role() -> None:
    """An ``<a>`` without a destination links nothing."""
    assert parse_roles("<p><a>Engineer</a></p>", SITE) == ()


@pytest.mark.parametrize("text", ["", "   ", "https://example.org/jobs/data-engineer"])
def test_an_anchor_without_a_title_of_its_own_is_titled_from_its_url(text: str) -> None:
    """An anchor whose text is empty, or the URL itself (Ionic's case), takes its segment."""
    html = f'<p><a href="https://example.org/jobs/data-engineer">{text}</a></p>'

    assert parse_roles(html, SITE) == (
        Role("Data engineer", "https://example.org/jobs/data-engineer"),
    )


@pytest.mark.parametrize(
    ("html", "role"),
    [
        (
            "<p>Engineer – https://example.org/jobs/1.</p>",
            Role("Engineer", "https://example.org/jobs/1"),
        ),
        (
            "<li>Apply: <em>https://example.org/jobs/1</em></li>",
            Role("Apply", "https://example.org/jobs/1"),
        ),
        (
            "<p>https://example.org/</p>",
            Role("example.org", "https://example.org/"),
        ),
        (
            "<p>https://example.org/open%20roles/</p>",
            Role("Open roles", "https://example.org/open%20roles/"),
        ),
        (
            "<li><p>Engineer | https://example.org/1</p>",  # left open
            Role("Engineer", "https://example.org/1"),
        ),
    ],
)
def test_a_block_with_one_bare_url_is_a_role(html: str, role: Role) -> None:
    """A paragraph or item holding one bare URL is titled by the text before it, else the URL.

    Separators and sentence punctuation are trimmed, an inline tag is read through, the
    segment is decoded, a URL without a path takes its host, and a block the HTML leaves
    open still counts.
    """
    assert parse_roles(html, SITE) == (role,)


@pytest.mark.parametrize(
    ("html", "roles"),
    [
        ("<p>Engineer https://example.org/1 or Designer https://example.org/2</p>", ()),
        (
            '<p><a href="https://example.org/1">Engineer</a> https://example.org/2</p>',
            (Role("Engineer", "https://example.org/1"),),
        ),
        ("<div>Engineer | https://example.org/1</div>", ()),
        ("<p>Apply at http://.</p>", ()),
        ("<p>N/A</p>", ()),
    ],
)
def test_other_bare_urls_make_no_role(html: str, roles: tuple[Role, ...]) -> None:
    """Two URLs in a block, a URL beside an anchor or outside ``p``/``li``: no role of its own.

    The anchor beside a URL is still a role; a scheme followed only by punctuation is
    no URL.
    """
    assert parse_roles(html, SITE) == roles


@pytest.mark.parametrize(
    ("html", "roles"),
    [
        ("<p>https://example.org/one<br>https://example.org/two</p>", ()),
        (
            "<p>Senior<br>Engineer | https://example.org/x</p>",
            (Role("Senior Engineer", "https://example.org/x"),),
        ),
        (
            '<li><a href="https://e.org/a">Senior<br/>Engineer</a></li>',
            (Role("Senior Engineer", "https://e.org/a"),),
        ),
        (
            "<li>Engineer https://example.org/1<ul><li>Designer</li></ul>Remote</li>",
            (Role("Engineer", "https://example.org/1"),),
        ),
    ],
)
def test_a_line_break_separates_words_and_urls(
    html: str, roles: tuple[Role, ...]
) -> None:
    """A ``br`` or a nested block's edge splits the text, as a browser shows it (D-278).

    Two URLs a line apart are two URLs, so the block makes no role, a title split over
    two lines keeps its space, and a nested list's text does not run into the URL before
    it.
    """
    assert parse_roles(html, SITE) == roles


@pytest.mark.parametrize("tag", ["script", "style"])
def test_script_and_style_text_makes_no_role(tag: str) -> None:
    """A URL inside ``script`` or ``style`` is not visible, so it is no role, as html_md drops it."""
    html = f"<p>Engineer <{tag}>https://example.org/fake</{tag}></p>"

    assert parse_roles(html, SITE) == ()


def test_script_text_is_neither_a_title_nor_searched() -> None:
    """Script text inside an anchor stays out of its title and of the listing's search text."""
    html = (
        '<p><a href="https://example.org/job">Engineer<script>nofollow</script></a></p>'
    )

    read = read_listing(replace(listing("Bloomberg"), description=html), SITE, str)

    assert read.roles == (Role("Engineer", "https://example.org/job"),)
    assert "nofollow" not in read.search_text


@pytest.mark.parametrize(
    ("html", "titles"),
    [
        (
            (
                "<ul><li>Engineer https://example.org/eng"
                "<ul><li>Designer https://example.org/des</li></ul></li></ul>"
            ),
            ["Engineer", "Designer"],
        ),
        (
            (
                "<ul><li>Engineer<ul><li>Designer https://example.org/des</li></ul>"
                "https://example.org/eng</li></ul>"
            ),
            ["Designer", "Engineer"],
        ),
        (
            (
                '<ul><li><a href="https://example.org/eng">Engineer</a>'
                "<ul><li>Designer https://example.org/des</li></ul></li></ul>"
            ),
            ["Engineer", "Designer"],
        ),
    ],
)
def test_nested_roles_keep_the_listings_order(html: str, titles: list[str]) -> None:
    """Roles come in the order their link appears, though an inner item ends first (D-278)."""
    assert [role.title for role in parse_roles(html, SITE)] == titles


def test_a_long_form_listing_has_no_roles() -> None:
    """A listing with a heading is a job description: its anchors and URLs are not roles."""
    html = (
        "<h2>Staff Engineer</h2>"
        '<p><a href="https://example.org/">Example</a> builds things.</p>'
        "<p><strong>Apply:</strong> https://example.org/jobs/1</p>"
    )

    assert parse_roles(html, SITE) == ()


def test_the_2026_long_form_listings_keep_their_markdown() -> None:
    """SerpApi's and marimo's descriptions show as Markdown, headings and all."""
    for sponsor in ("SerpApi", "marimo"):
        assert listing(sponsor).description_md.startswith("## ")
