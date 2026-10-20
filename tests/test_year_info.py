"""Tests for the info pages' year data (D-263): ``year_info``, as ``config`` runs it.

Every year's load runs the info pages' checks on the content it built, so a page's
rules fail the load as soon as its table lands; the Wi-Fi table's rules (D-280) are the
first.
"""

import shutil
from pathlib import Path

import pytest

from pycon_us import config
from pycon_us.config import Content, YearDataError, load_year
from pycon_us.year_info import WifiInfo, check_info
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
