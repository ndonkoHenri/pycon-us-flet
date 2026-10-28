"""Tests for the sponsors door staff scan for: ``core/lead_sponsors.py`` and its fetch.

``parse_sponsors`` reads ``lead_sponsors``' reply as Ionic did, without its bugs (API-09):
quotes stripped from names, ids kept as strings, bad entries left out; the filter finds
by name or booth among 150 sponsors (LEAD-05's "usable with 100+"); the saved choice
round-trips through ``pycon.staff_sponsor`` (STORE-11). ``fetch_sponsors`` runs against
the mock over its real transport, signed in as the seeded staff account.
"""

import pytest

from pycon_us.core.lead_sponsors import (
    LeadSponsor,
    filter_sponsors,
    from_stored,
    parse_sponsors,
    to_stored,
)
from pycon_us.services.api import ApiError
from pycon_us.staff_sponsor import fetch_sponsors
from tests.api_clients import client_for, replying, signed_in
from tests.mock_calls import call, state_at

EXAMPLE = LeadSponsor("1", "Example Corp", "101", "https://example.com/logo.png")


def test_names_lose_their_quotes_and_entries_sort_by_name() -> None:
    """One ``"`` goes from each end, as Ionic's ``/^"|"$/``; the list sorts by name."""
    reply = {
        "sponsors": [
            {"id": 3, "name": "Sample Systems"},
            {"id": 2, "name": '"Quoted Labs"'},
            {"id": 1, "name": "Example Corp", "booth_number": "101", "logo_url": "u"},
            {"id": 4, "name": '""Twice""'},
        ]
    }
    assert parse_sponsors(reply) == (
        LeadSponsor("4", '"Twice"'),  # one pair only, as Ionic: `"` sorts first
        LeadSponsor("1", "Example Corp", "101", "u"),
        LeadSponsor("2", "Quoted Labs"),
        LeadSponsor("3", "Sample Systems"),
    )


def test_booth_and_logo_are_optional_and_ids_are_strings() -> None:
    """A missing, null or empty booth or logo is None; an int id or booth is text."""
    reply = {
        "sponsors": [
            {"id": 7, "name": "A", "booth_number": 12, "logo_url": None},
            {"id": "8", "name": "B", "booth_number": "", "logo_url": ""},
        ]
    }
    assert parse_sponsors(reply) == (
        LeadSponsor("7", "A", "12", None),
        LeadSponsor("8", "B", None, None),
    )


@pytest.mark.parametrize(
    "entry",
    [
        "Example Corp",
        {"name": "No id"},
        {"id": True, "name": "A bool id"},
        {"id": 5.5, "name": "A float id"},
        {"id": 5},
        {"id": 5, "name": '""'},
        {"id": 5, "name": 7},
    ],
)
def test_a_malformed_entry_is_left_out(entry: object) -> None:
    """An entry without a usable id or name goes; the good one beside it stays."""
    reply = {"sponsors": [entry, {"id": 1, "name": "Example Corp"}]}
    assert parse_sponsors(reply) == (LeadSponsor("1", "Example Corp"),)


def test_a_repeated_id_keeps_the_first_entry() -> None:
    """Two entries with one id are one sponsor, the first read."""
    reply = {"sponsors": [{"id": 1, "name": "First"}, {"id": "1", "name": "Again"}]}
    assert parse_sponsors(reply) == (LeadSponsor("1", "First"),)


@pytest.mark.parametrize("reply", [None, [], {}, {"sponsors": {}}, {"data": []}])
def test_a_reply_without_a_sponsors_list_is_refused(reply: object) -> None:
    """Not ``{"sponsors": [...]}``: a ``TypeError``, which the fetch makes an error."""
    with pytest.raises(TypeError):
        parse_sponsors(reply)


def test_the_mock_s_sponsors_parse_sorted_and_unquoted() -> None:
    """The mock's three sponsors, its quoted one plain, booth and logo as seeded."""
    status, reply = call(state_at(), "GET", "lead_retrieval/sponsors/", "staff")
    assert status == 200
    sponsors = parse_sponsors(reply)
    assert [s.name for s in sponsors] == [
        "Example Corp",
        "Quoted Labs",
        "Sample Systems",
    ]
    assert [s.booth for s in sponsors] == ["101", "214", None]
    assert [bool(s.logo_url) for s in sponsors] == [True, False, False]


def generated(count: int) -> tuple[LeadSponsor, ...]:
    """Return ``count`` sponsors, "Sponsor 000" at booth 1000 onwards, and Sample Systems."""
    return parse_sponsors(
        {
            "sponsors": [
                {"id": n, "name": f"Sponsor {n:03}", "booth_number": str(1000 + n)}
                for n in range(count)
            ]
            + [{"id": 999, "name": "Sample Systems"}]
        }
    )


def test_the_filter_finds_by_name_or_booth_among_150() -> None:
    """Among 150 sponsors, a word finds the name or booth that holds it, folded."""
    sponsors = generated(150)
    assert len(sponsors) == 151
    assert [s.name for s in filter_sponsors(sponsors, "sam")] == ["Sample Systems"]
    assert [s.name for s in filter_sponsors(sponsors, "SPONSOR 149")] == ["Sponsor 149"]
    assert [s.booth for s in filter_sponsors(sponsors, "1007")] == ["1007"]
    assert filter_sponsors(sponsors, "nobody") == ()


def test_a_blank_filter_keeps_the_list_itself() -> None:
    """No word to match: the same tuple, so the screen knows no filter applies."""
    sponsors = generated(3)
    assert filter_sponsors(sponsors, "  ") is sponsors


def test_the_choice_round_trips_without_its_booth() -> None:
    """``{id, name, logo_url}`` is kept; the booth is not (the chip shows none)."""
    stored = to_stored(EXAMPLE)
    assert stored == {
        "id": "1",
        "name": "Example Corp",
        "logo_url": "https://example.com/logo.png",
    }
    assert from_stored(stored) == LeadSponsor(
        "1", "Example Corp", logo_url="https://example.com/logo.png"
    )


@pytest.mark.parametrize(
    "stored",
    [{}, {"id": 1, "name": "A"}, {"id": "1"}, {"id": "", "name": "A"}],
)
def test_nothing_or_a_broken_choice_reads_as_none(stored: dict[str, object]) -> None:
    """Nothing chosen, or a value that isn't one: no sponsor."""
    assert from_stored(stored) is None


async def test_fetch_sponsors_reads_the_mock_signed_in_as_staff() -> None:
    """The signed call reaches the mock's route and reads its three sponsors."""
    client, recorder, _ = await signed_in("staff")
    sponsors = await fetch_sponsors(client)
    assert [s.id for s in sponsors] == ["1", "2", "3"]
    assert recorder.sent[-1].url.path == "/2026/api/v1/lead_retrieval/sponsors/"
    await client.aclose()


async def test_a_reply_without_sponsors_is_an_api_error() -> None:
    """A 200 that isn't a sponsors list is an ``ApiError`` the picker says it couldn't load."""
    client = client_for(replying(200, b'{"data": []}'))
    with pytest.raises(ApiError):
        await fetch_sponsors(client)
    await client.aclose()


async def test_an_account_without_a_lead_flag_is_refused() -> None:
    """The mock answers 403 to the attendee: an ``ApiError``, not a list."""
    client, _, _ = await signed_in("attendee")
    with pytest.raises(ApiError) as caught:
        await fetch_sponsors(client)
    assert caught.value.is_auth
    await client.aclose()
