"""Tests for the year data of About the PSF and Social (D-283, D-284): `year_links`.

Each page's table and its rules; the info pages' load and Help & safety and Wi-Fi
are `tests/test_year_info.py`'s.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us import config
from pycon_us.config import Content, YearDataError, load_year
from pycon_us.ui.brands import BRANDS
from pycon_us.year_info import check_info
from pycon_us.year_links import (
    PSF_SECTIONS,
    SOCIAL_SECTIONS,
    PsfInfo,
    PsfLink,
    SocialInfo,
    SocialLink,
    check_social,
)
from pycon_us.year_schema import build

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)

# ------------------------------------------------------------------ About the PSF

FILE = "2026/content.toml"
PSF = load_year(2026).content.psf


def psf_with(**fields: Any) -> Content:
    """2026's content with its first link's `fields` changed."""
    assert PSF is not None
    first = replace(PSF.links[0], **fields)
    return Content(psf=replace(PSF, links=(first, *PSF.links[1:])))


def test_2026_has_the_mission_donate_and_links_in_every_section() -> None:
    """2026's `[psf]` has the mission, the donate page and links in all three sections."""
    assert PSF is not None
    assert PSF.mission.startswith("The mission of the Python Software Foundation")
    assert PSF.donate_url == "https://www.python.org/psf/donations/"
    assert {link.section for link in PSF.links} == set(PSF_SECTIONS)


def test_2025_has_no_psf_table() -> None:
    """2025 has no `[psf]`, so its page shows the feed's block (D-263)."""
    assert load_year(2025).content.psf is None


def test_2026_links_to_donate_once_and_to_the_blog_over_https() -> None:
    """Donate is only the button (Ionic linked it twice), and the feed's http blog is https."""
    assert PSF is not None
    urls = [link.url for link in PSF.links]
    assert PSF.donate_url not in urls
    assert "https://pyfound.blogspot.com/" in urls
    assert all(url.startswith("https://") for url in urls)


@pytest.mark.parametrize("year", YEARS)
def test_psf_brands_are_bundled_marks_and_icons_are_material_icons(year: int) -> None:
    """Each year's PSF links have a brand or an icon: a bundled mark, or one Flet knows.

    The loader imports no Flet, so this is where a misspelt name in any bundled
    year's `[psf]` fails, before the page would fail to draw its row.
    """
    psf = load_year(year).content.psf
    if psf is None:
        pytest.skip(f"{year} has no [psf]")
    for link in psf.links:
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
        (
            {"label": "X"},
            r"psf\.links\[\d+\]\.label: 'X' gives the same identifier as 'X'$",
        ),
        # Another label with X's key, psf.link.x: one identifier for two rows.
        (
            {"label": "x"},
            r"psf\.links\[\d+\]\.label: 'X' gives the same identifier as 'x'$",
        ),
        (
            {"label": "python-org"},
            (
                r"psf\.links\[\d+\]\.label: 'python\.org' gives the same identifier "
                r"as 'python-org'$"
            ),
        ),
        (
            {"label": "!!!"},
            r"psf\.links\[0\]\.label: '!!!' has no letter or digit for its key$",
        ),
        (
            {"brand": "python", "icon": "LANGUAGE"},
            r"psf\.links\[0\]: give a brand or an icon, not both$",
        ),
    ],
)
def test_a_link_that_breaks_a_rule_fails_the_check(
    fields: dict[str, Any], message: str
) -> None:
    """A link that is not https, has an unknown section or repeats a row key is refused."""
    with pytest.raises(YearDataError, match=rf"^{FILE}: {message}"):
        check_info(psf_with(**fields), load_year(2026).conference, FILE)


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
        check_info(content, load_year(2026).conference, FILE)


def test_a_broken_psf_table_fails_the_year_s_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rules run on the load itself: a bad link fails `load_year()` (D-263)."""
    broken = psf_with(section="news")
    original = config.build

    def build_broken(cls: type, raw: object, file: str, key: str = "") -> object:
        """Build as the loader does, but hand back the broken content for `Content`."""
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
    """`brand`, `icon` and `app` are optional: a link may give none of them."""
    raw = {"section": "follow", "label": "Blog", "url": "https://pyfound.blogspot.com/"}
    link = build(PsfLink, raw, FILE, "psf.links[0]")
    assert (link.brand, link.icon, link.app) == (None, None, False)


# ------------------------------------------------------------------ Social (D-284)

SOCIAL = load_year(2026).content.social


def social(**changes: object) -> SocialInfo:
    """2026's `[social]` with `changes` applied to the table itself."""
    assert SOCIAL is not None
    return replace(SOCIAL, **changes)  # pyright: ignore[reportArgumentType]


def with_link(**changes: object) -> SocialInfo:
    """2026's `[social]` with `changes` applied to its first link."""
    assert SOCIAL is not None
    first = replace(SOCIAL.links[0], **changes)  # pyright: ignore[reportArgumentType]
    return replace(SOCIAL, links=(first, *SOCIAL.links[1:]))


def test_2026_has_the_hashtags_and_the_links_of_every_section() -> None:
    """2026's table passes the checks, with both hashtags and links in each section."""
    assert SOCIAL is not None
    check_social(SOCIAL, "2026/content.toml")
    assert SOCIAL.hashtags == ("#PyConUS", "#PyConUS2026")
    assert {link.section for link in SOCIAL.links} == set(SOCIAL_SECTIONS)


def test_2026_s_linkedin_link_is_the_feed_s_without_its_stray_bracket() -> None:
    """The feed's `linkedin.com/company/thepsf]` is fixed in the data (INFO-10)."""
    assert SOCIAL is not None
    urls = [link.url for link in SOCIAL.links]
    assert "https://www.linkedin.com/company/thepsf/" in urls
    assert not any("]" in url for url in urls)


def test_2025_has_no_social_table() -> None:
    """2025 has no `[social]`: its page falls back to the feed's block."""
    assert load_year(2025).content.social is None


@pytest.mark.parametrize("year", YEARS)
def test_every_brand_names_a_bundled_mark(year: int) -> None:
    """Each link's brand is a key of `BRANDS`, so its row draws a mark (D-264).

    The loader stays free of Flet, so this test, not the loader, holds it, as
    `test_config_tracks.py` holds the track icons.
    """
    table = load_year(year).content.social
    for link in table.links if table is not None else ():
        assert not link.brand or link.brand in BRANDS, link.key


def test_a_link_s_key_is_its_section_and_its_label_in_snake_case() -> None:
    """A link's identifier key: `pycon_mastodon`, `blogs_pycon_us_blog`."""
    link = SocialLink("blogs", "PyCon US blog", "pycon.blogspot.com", "https://x.org/")
    assert link.key == "blogs_pycon_us_blog"
    assert with_link().links[0].key == "pycon_mastodon"


@pytest.mark.parametrize(
    ("table", "message"),
    [
        (
            with_link(url="http://fosstodon.org/@pycon"),
            r"social.links\[0\].url: expected an https:// URL",
        ),
        (
            with_link(url="mailto:a@b.org"),
            r"social.links\[0\].url: expected an https:// URL",
        ),
        (
            with_link(section="python"),
            r"social.links\[0\].section: 'python' is not one of",
        ),
        (with_link(label=" "), r"social.links\[0\].label: is empty"),
        (with_link(handle=""), r"social.links\[0\].handle: is empty"),
        (with_link(brand="Mastodon"), r"social.links\[0\].brand: 'Mastodon'"),
        (
            social(hashtags=("PyConUS",)),
            r"social.hashtags\[0\]: 'PyConUS' is not a hashtag",
        ),
        (
            social(hashtags=("#PyCon US",)),
            r"social.hashtags\[0\]: '#PyCon US' is not a hashtag",
        ),
        (
            social(hashtags=("#PyConUS", "#pyconus")),
            r"social.hashtags\[1\]: duplicate hashtag '#pyconus'",
        ),
        (social(hashtags=(), links=()), r"social: is empty"),
    ],
)
def test_a_broken_social_rule_names_the_file_and_the_key(
    table: SocialInfo, message: str
) -> None:
    """Each `[social]` rule fails with the file and the key of what breaks it."""
    with pytest.raises(YearDataError, match=rf"^2026/content.toml: {message}"):
        check_social(table, "2026/content.toml")


def test_two_links_with_one_identifier_are_refused() -> None:
    """Two rows of a section with one label would share `social.link.<key>`."""
    assert SOCIAL is not None
    table = replace(SOCIAL, links=(*SOCIAL.links, SOCIAL.links[0]))
    with pytest.raises(YearDataError, match=r"label: 'Mastodon' is already in 'pycon'"):
        check_social(table, "2026/content.toml")


def test_the_load_refuses_a_broken_social_table(tmp_path: Path) -> None:
    """A `[social]` with an unknown section fails `load_year()` itself."""
    for name in ("conference.toml", "content.toml"):
        (tmp_path / "2026").mkdir(exist_ok=True)
        text = (config.DATA_DIR / "2026" / name).read_text()
        if name == "content.toml":
            text = text.replace('section = "blogs"', 'section = "podcasts"', 1)
        (tmp_path / "2026" / name).write_text(text)
    with pytest.raises(YearDataError, match=r"section: 'podcasts' is not one of"):
        load_year(2026, tmp_path)
