"""Tests for the info pages' year data (D-263): ``year_info``, as ``config`` runs it.

Every year's load runs the info pages' checks on the content and conference it built, so
a page's rules fail the load. The venue hours' own rules are ``tests/test_year_hours.py``.
"""

import pytest

from pycon_us import config
from pycon_us.config import ConferenceInfo, Content, YearDataError, load_year
from pycon_us.year_info import check_info

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


@pytest.mark.parametrize("year", YEARS)
def test_every_year_s_load_checks_its_info_pages(
    monkeypatch: pytest.MonkeyPatch, year: int
) -> None:
    """Each year's load passes its built content, conference and file to ``check_info()``."""
    calls: list[tuple[Content, ConferenceInfo, str]] = []

    def spy(content: Content, conference: ConferenceInfo, file: str) -> None:
        """Record the call, then check as the loader would."""
        calls.append((content, conference, file))
        check_info(content, conference, file)

    monkeypatch.setattr(config, "check_info", spy)
    data = load_year(year)
    assert calls == [(data.content, data.conference, f"{year}/content.toml")]


def test_a_broken_info_rule_fails_the_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``YearDataError`` from the info pages' checks is the load's error, unchanged."""

    def broken(content: Content, conference: ConferenceInfo, file: str) -> None:
        """Refuse the content, as a page's rule would."""
        raise YearDataError(f"{file}: wifi.password: is empty")

    monkeypatch.setattr(config, "check_info", broken)
    with pytest.raises(YearDataError, match=r"^2026/content.toml: wifi.password"):
        load_year(2026)
