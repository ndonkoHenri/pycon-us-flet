"""Tests for the info pages' year data (D-263): ``year_info``, as ``config`` runs it.

Every year's load runs the info pages' checks on the content it built, so a page's
rules fail the load as soon as its table lands; then each page's table and its rules:
Wi-Fi's (D-280) and Social's (D-284).
"""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from pycon_us import config
from pycon_us.config import Content, YearDataError, load_year
from pycon_us.ui.brands import BRANDS
from pycon_us.year_info import (
    SOCIAL_SECTIONS,
    SocialInfo,
    SocialLink,
    WifiInfo,
    check_info,
    check_social,
)
from pycon_us.year_schema import build
from tests.feeds import processed

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


def test_2026_bundles_the_wifi_its_feed_block_names() -> None:
    """2026's ``[wifi]`` holds the network and password of the feed's own block."""
    assert load_year(2026).content.wifi == WifiInfo("PyConUS26", "pyconLB2026")
    block = processed(2026).content_md["wifi"]
    assert "`PyConUS26`" in block and "`pyconLB2026`" in block


def test_2025_has_no_wifi_table() -> None:
    """2025 bundles no Wi-Fi: its page falls back to the feed (``ui.info_page``)."""
    assert load_year(2025).content.wifi is None


@pytest.mark.parametrize("key", ["network", "password"])
@pytest.mark.parametrize("blank", ["", " ", "\t\n"])
def test_a_blank_wifi_value_is_refused_naming_the_file_and_key(
    key: str, blank: str
) -> None:
    """A blank network or password fails with the file and the key, never shows."""
    values = {"network": "PyConUS26", "password": "pyconLB2026", key: blank}
    content = Content(wifi=WifiInfo(**values))
    with pytest.raises(
        YearDataError, match=rf"^2026/content.toml: wifi.{key}: is empty$"
    ):
        check_info(content, "2026/content.toml")


def test_a_blank_wifi_value_in_the_file_fails_the_load(tmp_path: Path) -> None:
    """The rule runs on load: a ``[wifi]`` with an empty password fails ``load_year()``."""
    shutil.copytree(config.DATA_DIR / "2026", tmp_path / "2026")
    content = tmp_path / "2026" / "content.toml"
    text = content.read_text()
    assert 'password = "pyconLB2026"' in text
    content.write_text(text.replace('password = "pyconLB2026"', 'password = ""'))
    with pytest.raises(YearDataError, match=r"^2026/content.toml: wifi.password: "):
        load_year(2026, tmp_path)


def test_a_wifi_table_needs_both_values() -> None:
    """The schema refuses a ``[wifi]`` without its password, naming the key."""
    with pytest.raises(YearDataError, match=r"^2026/content.toml: wifi.password: "):
        build(Content, {"wifi": {"network": "PyConUS26"}}, "2026/content.toml")


# ------------------------------------------------------------------ Social (D-284)

SOCIAL = load_year(2026).content.social


def social(**changes: object) -> SocialInfo:
    """2026's ``[social]`` with ``changes`` applied to the table itself."""
    assert SOCIAL is not None
    return replace(SOCIAL, **changes)  # pyright: ignore[reportArgumentType]


def with_link(**changes: object) -> SocialInfo:
    """2026's ``[social]`` with ``changes`` applied to its first link."""
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
    """The feed's ``linkedin.com/company/thepsf]`` is fixed in the data (INFO-10)."""
    assert SOCIAL is not None
    urls = [link.url for link in SOCIAL.links]
    assert "https://www.linkedin.com/company/thepsf/" in urls
    assert not any("]" in url for url in urls)


def test_2025_has_no_social_table() -> None:
    """2025 has no ``[social]``: its page falls back to the feed's block."""
    assert load_year(2025).content.social is None


@pytest.mark.parametrize("year", YEARS)
def test_every_brand_names_a_bundled_mark(year: int) -> None:
    """Each link's brand is a key of ``BRANDS``, so its row draws a mark (D-264).

    The loader stays free of Flet, so this test, not the loader, holds it, as
    ``test_config.py`` holds the track icons.
    """
    table = load_year(year).content.social
    for link in table.links if table is not None else ():
        assert not link.brand or link.brand in BRANDS, link.key


def test_a_link_s_key_is_its_section_and_its_label_in_snake_case() -> None:
    """A link's identifier key: ``pycon_mastodon``, ``blogs_pycon_us_blog``."""
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
    """Each ``[social]`` rule fails with the file and the key of what breaks it."""
    with pytest.raises(YearDataError, match=rf"^2026/content.toml: {message}"):
        check_social(table, "2026/content.toml")


def test_two_links_with_one_identifier_are_refused() -> None:
    """Two rows of a section with one label would share ``social.link.<key>``."""
    assert SOCIAL is not None
    table = replace(SOCIAL, links=(*SOCIAL.links, SOCIAL.links[0]))
    with pytest.raises(YearDataError, match=r"label: 'Mastodon' is already in 'pycon'"):
        check_social(table, "2026/content.toml")


def test_the_load_refuses_a_broken_social_table(tmp_path: Path) -> None:
    """A ``[social]`` with an unknown section fails ``load_year()`` itself."""
    for name in ("conference.toml", "content.toml"):
        (tmp_path / "2026").mkdir(exist_ok=True)
        text = (config.DATA_DIR / "2026" / name).read_text()
        if name == "content.toml":
            text = text.replace('section = "blogs"', 'section = "podcasts"', 1)
        (tmp_path / "2026" / name).write_text(text)
    with pytest.raises(YearDataError, match=r"section: 'podcasts' is not one of"):
        load_year(2026, tmp_path)
