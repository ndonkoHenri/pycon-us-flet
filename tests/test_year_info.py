"""Tests for the info pages' year data (D-263): ``year_info``, as ``config`` runs it.

Every year's load runs the info pages' checks on the content it built, so a page's
rules fail the load. Help & safety's tables (D-281) are checked here through the
loader, from a copy of the 2026 data with one entry changed, so each refusal is the
error a broken ``content.toml`` would give.
"""

import shutil
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from pycon_us import config
from pycon_us.config import Content, YearDataError, load_year
from pycon_us.year_info import SafetyContact, check_info

EMAIL_CONTACT = {
    "label": "Email the Code of Conduct team",
    "kind": "mailto",
    "value": "pycon-us-report@python.org",
    "source": "https://policies.python.org/us.pycon.org/code-of-conduct/",
    "checked": date(2026, 10, 20),
}
"""A valid ``[[safety_contacts]]`` entry, which each test breaks one way."""

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


def toml_value(value: object) -> str:
    """Return ``value`` written as TOML: a string, a date or a list of them."""
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise TypeError(value)


def load_with(
    tmp_path: Path,
    *,
    contacts: list[dict[str, Any]] | None = None,
    help_table: dict[str, Any] | None = None,
) -> config.YearData:
    """Load 2026 from a copy whose Help & safety tables are replaced by these.

    Args:
        tmp_path: Where the copy goes.
        contacts: The ``[[safety_contacts]]`` entries; None keeps none.
        help_table: The ``[help]`` table; None keeps none.
    """
    folder = tmp_path / "2026"
    shutil.copytree(config.DATA_DIR / "2026", folder)
    path = folder / "content.toml"
    text = path.read_text(encoding="utf-8")
    start = text.index("[[safety_contacts]]")
    end = text.index("# Shift the displayed start")
    lines = []
    for contact in contacts or []:
        lines.append("[[safety_contacts]]")
        lines += [f"{key} = {toml_value(value)}" for key, value in contact.items()]
    if help_table is not None:
        lines.append("[help]")
        lines += [f"{key} = {toml_value(value)}" for key, value in help_table.items()]
    path.write_text(text[:start] + "\n".join(lines) + "\n\n" + text[end:], "utf-8")
    return load_year(2026, data_dir=tmp_path)


def help_2026() -> dict[str, Any]:
    """The 2026 ``[help]`` table as the file has it."""
    with (config.DATA_DIR / "2026" / "content.toml").open("rb") as stream:
        return dict(tomllib.load(stream)["help"])


def test_2026_lists_the_report_email_and_no_phone_line() -> None:
    """2026 ships the email alone: the hotline is on no public page (D-45, D-281)."""
    contacts = load_year(2026).content.safety_contacts
    assert [(c.kind, c.value) for c in contacts] == [
        ("mailto", "pycon-us-report@python.org")
    ]
    assert contacts[0].target == "mailto:pycon-us-report@python.org"
    assert contacts[0].source.startswith("https://policies.python.org/")


def test_2026_has_the_help_lines_and_links() -> None:
    """2026's ``[help]`` builds with every line and both https links."""
    info = load_year(2026).content.help
    assert info is not None
    assert info.coc_url == "https://policies.python.org/us.pycon.org/code-of-conduct/"
    assert info.procedures_url.endswith("/Procedures-for-Reporting-Incidents/")
    assert "staff" in info.in_person


def test_2026_s_staff_line_says_emergency_services_first() -> None:
    """In danger, the card points to emergency services before reporting (INFO-07).

    From the Procedures page, which opens with it: call the appropriate crisis or
    police number, and a volunteer or staff member helps find it; PyCon US is not
    equipped to handle emergencies.
    """
    info = load_year(2026).content.help
    assert info is not None
    assert info.in_person.startswith("If someone is in danger")
    assert "emergency services" in info.in_person


def test_help_without_a_contact_is_refused(tmp_path: Path) -> None:
    """``[help]`` needs a contact: the page's first stop is the card (D-281)."""
    with pytest.raises(YearDataError, match=r"content\.toml: help: needs at least one"):
        load_with(tmp_path, help_table=help_2026())


def stale_contacts(year: int, data_dir: Path, today: date) -> list[str]:
    """Return the year's contacts not re-checked for it, as D-45 asks, one line each.

    A contact is stale when its check date is after ``today``, or not after both the
    year before's last day and that year's check dates: a folder copied forward
    without a fresh check keeps last year's date and fails. The rule lives in the
    tests, not the loader, since the device has no reason to read last year's data.

    Args:
        year: The year whose contacts to look at.
        data_dir: The folder that holds the year folders.
        today: The day the check runs.
    """
    contacts = load_year(year, data_dir).content.safety_contacts
    since = None
    if (data_dir / str(year - 1)).is_dir():
        before = load_year(year - 1, data_dir)
        since = max(
            [before.conference.last_day]
            + [c.checked for c in before.content.safety_contacts]
        )
    problems = []
    for contact in contacts:
        if contact.checked > today:
            problems.append(f"{contact.kind}: checked {contact.checked}, in the future")
        elif since is not None and contact.checked <= since:
            problems.append(
                f"{contact.kind}: checked {contact.checked}, not after {since}"
            )
    return problems


@pytest.mark.parametrize("year", YEARS)
def test_every_year_s_safety_contacts_were_checked_for_it(year: int) -> None:
    """Each bundled year's contacts were checked since the year before (D-45, D-281)."""
    # UTC is ahead of every US zone, so a check made today anywhere there passes.
    today = datetime.now(UTC).date()
    assert stale_contacts(year, config.DATA_DIR, today) == []


def copy_forward(tmp_path: Path, checked: date | None = None) -> Path:
    """Copy 2026 to ``tmp_path`` as 2026 and as a 2027 with its dates a year on.

    Args:
        tmp_path: Where the year folders go.
        checked: The 2027 contacts' check date; None keeps 2026's, as a rollover
            that forgot the check would.
    """
    shutil.copytree(config.DATA_DIR / "2026", tmp_path / "2026")
    folder = tmp_path / "2027"
    shutil.copytree(config.DATA_DIR / "2026", folder)
    conference = folder / "conference.toml"
    text = conference.read_text(encoding="utf-8")
    text = text.replace("year = 2026", "year = 2027").replace("2026-05-", "2027-05-")
    conference.write_text(text, encoding="utf-8")
    if checked is not None:
        content = folder / "content.toml"
        text = content.read_text(encoding="utf-8")
        text = text.replace("checked = 2026-10-20", f"checked = {checked.isoformat()}")
        content.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_contact_copied_forward_unchecked_is_stale(tmp_path: Path) -> None:
    """A 2027 that keeps 2026's check date was never re-checked, so the test fails."""
    data_dir = copy_forward(tmp_path)
    assert stale_contacts(2027, data_dir, date(2027, 1, 10)) == [
        "mailto: checked 2026-10-20, not after 2026-10-20"
    ]


def test_a_contact_re_checked_after_the_year_before_is_fresh(tmp_path: Path) -> None:
    """A check made any time after the previous PyCon and its check counts."""
    data_dir = copy_forward(tmp_path, checked=date(2026, 12, 1))
    assert stale_contacts(2027, data_dir, date(2027, 1, 10)) == []


def test_a_check_date_in_the_future_is_stale(tmp_path: Path) -> None:
    """A check date after today is a typo, not a check."""
    data_dir = copy_forward(tmp_path, checked=date(2027, 2, 1))
    assert stale_contacts(2027, data_dir, date(2027, 1, 10)) == [
        "mailto: checked 2027-02-01, in the future"
    ]


def test_a_year_without_the_tables_has_none(tmp_path: Path) -> None:
    """Both tables are optional: the page then shows the feed's block (D-263)."""
    content = load_with(tmp_path).content
    assert content.safety_contacts == ()
    assert content.help is None


def test_a_tel_contact_opens_its_number() -> None:
    """A ``tel`` contact's target is ``tel:`` and the number; an https one the URL."""
    phone = SafetyContact(**{**EMAIL_CONTACT, "kind": "tel", "value": "+15625550100"})
    assert phone.target == "tel:+15625550100"
    web = SafetyContact(**{**EMAIL_CONTACT, "kind": "https", "value": "https://a.org/"})
    assert web.target == "https://a.org/"


@pytest.mark.parametrize("missing", ["source", "checked"])
def test_a_contact_without_its_source_or_check_date_is_refused(
    tmp_path: Path, missing: str
) -> None:
    """A safety contact names where it was verified and when, or the load fails."""
    contact = {k: v for k, v in EMAIL_CONTACT.items() if k != missing}
    with pytest.raises(
        YearDataError, match=rf"safety_contacts\[0\]\.{missing}: missing key"
    ):
        load_with(tmp_path, contacts=[contact])


@pytest.mark.parametrize(
    "source",
    ["http://policies.python.org/coc/", "policies.python.org/coc/", "https://"],
)
def test_a_contact_whose_source_is_not_an_https_page_is_refused(
    tmp_path: Path, source: str
) -> None:
    """The source is a public ``https://`` page with a host."""
    with pytest.raises(YearDataError, match=r"safety_contacts\[0\]\.source"):
        load_with(tmp_path, contacts=[{**EMAIL_CONTACT, "source": source}])


@pytest.mark.parametrize(
    "number", ["5626624082", "+1 562 662 4082", "+1-562-662-4082", "+0123456", "+1"]
)
def test_a_malformed_tel_is_refused(tmp_path: Path, number: str) -> None:
    """A phone number is E.164: ``+``, a country code, then digits only."""
    contact = {**EMAIL_CONTACT, "kind": "tel", "value": number}
    with pytest.raises(YearDataError, match=r"\.value: expected an E\.164 number"):
        load_with(tmp_path, contacts=[contact])


def test_an_e164_tel_loads(tmp_path: Path) -> None:
    """A well-formed number loads as written."""
    contact = {**EMAIL_CONTACT, "kind": "tel", "value": "+15625550100"}
    (loaded,) = load_with(tmp_path, contacts=[contact]).content.safety_contacts
    assert loaded.value == "+15625550100"


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("mailto", "pycon-us-report"),
        ("mailto", "mailto:a@b.org"),
        ("mailto", "a@b"),
        ("https", "http://a.org/"),
    ],
)
def test_a_value_its_kind_cannot_open_is_refused(
    tmp_path: Path, kind: str, value: str
) -> None:
    """An address is an address and a web page an ``https://`` URL."""
    contact = {**EMAIL_CONTACT, "kind": kind, "value": value}
    with pytest.raises(YearDataError, match=r"safety_contacts\[0\]\.value"):
        load_with(tmp_path, contacts=[contact])


def test_an_unknown_kind_is_refused(tmp_path: Path) -> None:
    """A contact is a phone number, an email address or a web page."""
    with pytest.raises(YearDataError, match=r"\.kind: 'sms' is not one of"):
        load_with(tmp_path, contacts=[{**EMAIL_CONTACT, "kind": "sms"}])


def test_two_contacts_of_one_kind_are_refused(tmp_path: Path) -> None:
    """One contact per kind: the row's identifier is ``help.report.<kind>``."""
    with pytest.raises(YearDataError, match=r"\[1\]\.kind: duplicate kind 'mailto'"):
        load_with(tmp_path, contacts=[EMAIL_CONTACT, EMAIL_CONTACT])


def test_a_blank_label_is_refused(tmp_path: Path) -> None:
    """A row says what a tap does."""
    with pytest.raises(YearDataError, match=r"safety_contacts\[0\]\.label: is empty"):
        load_with(tmp_path, contacts=[{**EMAIL_CONTACT, "label": " "}])


@pytest.mark.parametrize("key", ["in_person", "info_desk", "coc_summary"])
def test_a_blank_help_line_is_refused(tmp_path: Path, key: str) -> None:
    """Every line of ``[help]`` says something."""
    with pytest.raises(YearDataError, match=rf"help\.{key}: is empty"):
        load_with(
            tmp_path, contacts=[EMAIL_CONTACT], help_table={**help_2026(), key: ""}
        )


@pytest.mark.parametrize("key", ["coc_url", "procedures_url"])
def test_a_help_link_that_is_not_https_is_refused(tmp_path: Path, key: str) -> None:
    """The Code of Conduct's links are ``https://`` pages."""
    with pytest.raises(YearDataError, match=rf"help\.{key}: expected an https"):
        load_with(
            tmp_path,
            contacts=[EMAIL_CONTACT],
            help_table={**help_2026(), key: "http://a.org/"},
        )
