"""Tests for the info pages' year data (D-263): ``year_info``, as ``config`` runs it.

Every year's load runs the info pages' checks on the content it built, so a page's
rules fail the load; About the PSF's ``[psf]`` (D-283) is the first table with rules.
"""

from dataclasses import replace
from typing import Any

import flet as ft
import pytest

from pycon_us import config
from pycon_us.config import Content, YearDataError, load_year
from pycon_us.ui.brands import BRANDS
from pycon_us.year_info import PSF_SECTIONS, PsfInfo, PsfLink, check_info
from pycon_us.year_schema import build

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


@pytest.mark.parametrize("year", YEARS)
def test_every_year_s_load_checks_its_info_pages(
    monkeypatch: pytest.MonkeyPatch, year: int
) -> None:
    """Each year's load passes its built content and file name to ``check_info()``."""
    calls: list[tuple[Content, str]] = []

    def spy(content: Content, file: str) -> None:
        """Record the call, then check as the loader would."""
        calls.append((content, file))
        check_info(content, file)

    monkeypatch.setattr(config, "check_info", spy)
    data = load_year(year)
    assert calls == [(data.content, f"{year}/content.toml")]


def test_a_broken_info_rule_fails_the_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``YearDataError`` from the info pages' checks is the load's error, unchanged."""

    def broken(content: Content, file: str) -> None:
        """Refuse the content, as a page's rule would."""
        raise YearDataError(f"{file}: wifi.password: is empty")

    monkeypatch.setattr(config, "check_info", broken)
    with pytest.raises(YearDataError, match=r"^2026/content.toml: wifi.password"):
        load_year(2026)


# ------------------------------------------------------------------ About the PSF

FILE = "2026/content.toml"
PSF = load_year(2026).content.psf


def psf_with(**fields: Any) -> Content:
    """2026's content with its first link's ``fields`` changed."""
    assert PSF is not None
    first = replace(PSF.links[0], **fields)
    return Content(psf=replace(PSF, links=(first, *PSF.links[1:])))


def test_2026_has_the_mission_donate_and_links_in_every_section() -> None:
    """2026's ``[psf]`` has the mission, the donate page and links in all three sections."""
    assert PSF is not None
    assert PSF.mission.startswith("The mission of the Python Software Foundation")
    assert PSF.donate_url == "https://www.python.org/psf/donations/"
    assert {link.section for link in PSF.links} == set(PSF_SECTIONS)


def test_2025_has_no_psf_table() -> None:
    """2025 has no ``[psf]``, so its page shows the feed's block (D-263)."""
    assert load_year(2025).content.psf is None


def test_2026_links_to_donate_once_and_to_the_blog_over_https() -> None:
    """Donate is only the button (Ionic linked it twice), and the feed's http blog is https."""
    assert PSF is not None
    urls = [link.url for link in PSF.links]
    assert PSF.donate_url not in urls
    assert "https://pyfound.blogspot.com/" in urls
    assert all(url.startswith("https://") for url in urls)


def test_2026_brands_are_bundled_marks_and_icons_are_material_icons() -> None:
    """Each link has a brand or an icon: a bundled mark, or an icon Flet knows."""
    assert PSF is not None
    for link in PSF.links:
        assert (link.brand is None) != (link.icon is None), link.label
        if link.brand is not None:
            assert link.brand in BRANDS, link.label
        if link.icon is not None:
            assert hasattr(ft.Icons, link.icon), link.label


def test_2026_opens_only_the_social_profiles_in_their_apps() -> None:
    """Mastodon, X and LinkedIn open in their apps, and every other link in the browser."""
    assert PSF is not None
    assert [link.label for link in PSF.links if link.app] == [
        "Mastodon",
        "X",
        "LinkedIn",
    ]


HTTPS = "expected an https:// URL with a host$"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"url": "http://pyfound.blogspot.com/"}, rf"psf\.links\[0\]\.url: {HTTPS}"),
        ({"url": "https://"}, rf"psf\.links\[0\]\.url: {HTTPS}"),
        ({"url": "mailto:psf@python.org"}, rf"psf\.links\[0\]\.url: {HTTPS}"),
        (
            {"section": "news"},
            r"psf\.links\[0\]\.section: unknown section 'news', expected get_involved",
        ),
        ({"label": " "}, r"psf\.links\[0\]\.label: is empty$"),
        # Reported at the second use: X's own row, further down.
        ({"label": "X"}, r"psf\.links\[\d+\]\.label: 'X' is used twice$"),
        (
            {"brand": "python", "icon": "LANGUAGE"},
            r"psf\.links\[0\]: give a brand or an icon, not both$",
        ),
    ],
)
def test_a_link_that_breaks_a_rule_fails_the_check(
    fields: dict[str, Any], message: str
) -> None:
    """A link that is not https, has an unknown section or repeats a label is refused."""
    with pytest.raises(YearDataError, match=rf"^{FILE}: {message}"):
        check_info(psf_with(**fields), FILE)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"mission": " \n"}, r"psf\.mission: is empty$"),
        (
            {"donate_url": "http://www.python.org/psf/donations/"},
            rf"psf\.donate_url: {HTTPS}",
        ),
    ],
)
def test_a_blank_mission_or_an_http_donate_link_fails_the_check(
    fields: dict[str, Any], message: str
) -> None:
    """The mission must say something, and Donate must go to an https page."""
    assert PSF is not None
    content = Content(psf=replace(PSF, **fields))
    with pytest.raises(YearDataError, match=rf"^{FILE}: {message}"):
        check_info(content, FILE)


def test_a_broken_psf_table_fails_the_year_s_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rules run on the load itself: a bad link fails ``load_year()`` (D-263)."""
    broken = psf_with(section="news")
    original = config.build

    def build_broken(cls: type, raw: object, file: str, key: str = "") -> object:
        """Build as the loader does, but hand back the broken content for ``Content``."""
        return broken if cls is Content else original(cls, raw, file, key)

    monkeypatch.setattr(config, "build", build_broken)
    with pytest.raises(YearDataError, match=rf"^{FILE}: psf\.links\[0\]\.section: "):
        load_year(2026)


def test_a_link_with_an_unknown_key_fails_the_schema() -> None:
    """A link takes only its six keys: a misspelt one fails the load."""
    raw = {
        "mission": "To promote Python.",
        "donate_url": "https://www.python.org/psf/donations/",
        "links": [
            {"section": "follow", "label": "Blog", "url": "https://a.org/", "ap": 1}
        ],
    }
    with pytest.raises(YearDataError, match=rf"^{FILE}: psf\.links\[0\]\.ap: unknown"):
        build(PsfInfo, raw, FILE, "psf")


def test_a_link_without_brand_icon_or_app_is_a_plain_web_link() -> None:
    """``brand``, ``icon`` and ``app`` are optional: a link may give none of them."""
    raw = {"section": "follow", "label": "Blog", "url": "https://pyfound.blogspot.com/"}
    link = build(PsfLink, raw, FILE, "psf.links[0]")
    assert (link.brand, link.icon, link.app) == (None, None, False)
