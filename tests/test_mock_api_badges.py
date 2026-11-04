"""The printable mock-badge sheet: one QR code per seeded attendee (#666, D-391)."""

import re
from pathlib import Path

from pycon_us.config import YEAR
from tools.mock_api.badges import main, payload, qr_svg, sheet
from tools.mock_api.state import MockState


def test_every_seeded_attendee_is_encoded_once() -> None:
    """Each attendee's `code:validator` code, name and text appear exactly once."""
    state = MockState.from_seed()
    page = sheet(state.year, state.attendees.values())
    assert page.count("<svg") == len(state.attendees) == 4
    for attendee in state.attendees.values():
        assert page.count(qr_svg(payload(attendee))) == 1
        assert page.count(f'<p class="code">{payload(attendee)}</p>') == 1
        assert page.count(f"<h2>{attendee.full_name}</h2>") == 1


def test_the_payload_is_what_ionics_pages_split() -> None:
    """The payload is the access code, a colon, then the validator."""
    attendee = MockState.from_seed().attendees["MOCK0001"]
    assert payload(attendee) == "MOCK0001:v4l1d01"


def test_the_page_is_self_contained() -> None:
    """The sheet loads nothing: no scripts, links, images or URLs to fetch."""
    state = MockState.from_seed()
    page = sheet(state.year, state.attendees.values())
    assert not re.search(r"<script|<link|<img|src=|https?://(?!www\.w3\.org)", page)


def test_main_writes_the_sheet(tmp_path: Path) -> None:
    """`python -m tools.mock_api.badges --out FILE` writes the seeded sheet there."""
    out = tmp_path / "sheet" / "badges.html"
    main(["--out", str(out)])
    attendees = MockState.from_seed().attendees.values()
    assert out.read_text(encoding="utf-8") == sheet(YEAR, attendees)
