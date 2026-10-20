"""Properties of decoding single feed records (``core/records.py``; #150).

The decoding of whole feeds, with named edge cases, is tested in ``test_feed.py``. These
properties call the decoders directly, without the ``machine_tz`` fixture: hypothesis
cannot rerun a function-scoped fixture per example, and the decoders take the zone as an
argument. The end of summer time is checked here too, on the decoders' own (#513).
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import fields, is_dataclass
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core import records

ZONE = ZoneInfo("America/Los_Angeles")
SURROGATE = re.compile(r"[\ud800-\udfff]")
PAIR = re.compile(r"([\ud800-\udbff])([\udc00-\udfff])")


def expected(text: str) -> str:
    """Return ``text`` as UTF-16 reads it: a high-low pair joined, other surrogates U+FFFD.

    Written with regexes, independently of the helper under test.
    """
    joined = PAIR.sub(
        lambda pair: chr(
            0x10000 + (ord(pair[1]) - 0xD800) * 0x400 + ord(pair[2]) - 0xDC00
        ),
        text,
    )
    return SURROGATE.sub("\ufffd", joined)


# st.text() and st.characters() leave surrogates out, so the text is joined from
# characters drawn from the surrogate block as well.
_TEXT = st.lists(
    st.characters() | st.characters(min_codepoint=0xD800, max_codepoint=0xDFFF)
).map("".join)
_ID = st.integers(min_value=0) | _TEXT.filter(bool)


def strings_in(value: object) -> Iterator[str]:
    """Yield every string in ``value``, through tuples and the fields of records."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, tuple | list):
        for item in value:
            yield from strings_in(item)
    elif is_dataclass(value):
        for field in fields(value):
            yield from strings_in(getattr(value, field.name))


@given(text=_TEXT, key=_ID)
def test_no_decoded_string_holds_a_surrogate(text: str, key: int | str) -> None:
    """#150: strict UTF-8 (Flet's msgpack) cannot encode a surrogate code point."""
    speaker = {"id": key, "name": text, "photo": text, "bio": text}
    slot = {
        "conf_key": key,
        "name": text,
        "kind": text,
        "room": text,
        "description": text,
        "start": "2026-05-15T09:00:00-07:00",
        "end": "2026-05-15T09:30:00-07:00",
        "conf_url": text,
        "authors": [text, text],
        "speakers": [speaker],
    }
    open_space = {
        "conf_key": 1,
        "title": text,
        "description": text,
        "room_display": text,
        "room": text,
        "image_url": text,
    }
    poster = {"conf_key": key, "title": text, "description_html": text}
    nested_poster = {"conf_key": key, "name": text, "description": text}
    sprint = {
        "id": key,
        "name": text,
        "url": text,
        "description_html": text,
        "logo_url": text,
        "submitter": text,
    }
    listing = {
        "id": key,
        "sponsor_name": text,
        "sponsor_logo_url": text,
        "sponsor_level": text,
        "description_html": text,
    }
    decoded = [
        records.slot(slot, ZONE),
        records.open_space(open_space, ZONE),
        records.poster({**poster, "speakers": [speaker]}),
        records.nested_poster({**nested_poster, "speakers": [speaker]}),
        records.sprint(sprint),
        records.job_listing(listing),
    ]
    strings = list(strings_in(decoded))
    assert expected(text) in strings  # pairs are joined, the rest of the text kept
    assert not any(SURROGATE.search(string) for string in strings)


# ------------------------------------------------- the end of summer time (#513)

# 1:40 PDT (08:40Z) to 1:10 PST (09:10Z) on 2026-11-01: half an hour, across the change.
ACROSS_THE_CHANGE = ("2026-11-01T01:40:00-07:00", "2026-11-01T01:10:00-08:00")
# 1:40 PDT (08:40Z) to 1:10 PDT (08:10Z): it really ends first.
BACKWARDS = ("2026-11-01T01:40:00-07:00", "2026-11-01T01:10:00-07:00")


def timed_slot(start: str, end: str) -> dict[str, object]:
    """Return a minimal ``schedule`` record that runs from ``start`` to ``end``."""
    return {
        "conf_key": 142,
        "name": "Talk",
        "kind": "talk",
        "room": "Room 1",
        "start": start,
        "end": end,
    }


def timed_open_space(start: str, end: str) -> dict[str, object]:
    """Return a minimal ``open-spaces`` record that runs from ``start`` to ``end``."""
    return {"conf_key": 1, "title": "Open space", "start": start, "end": end}


DECODERS = [(records.slot, timed_slot), (records.open_space, timed_open_space)]


@pytest.mark.parametrize(("decode", "make"), DECODERS)
def test_a_session_across_the_end_of_summer_time_is_kept(
    decode: Callable[[object, ZoneInfo], records.Slot | records.OpenSpace],
    make: Callable[[str, str], dict[str, object]],
) -> None:
    """A session that ends 30 minutes after it starts is kept across the change.

    Its wall clocks read 1:40 to 1:10, which a wall-clock check would refuse.
    """
    decoded = decode(make(*ACROSS_THE_CHANGE), ZONE)
    assert decoded.start is not None and decoded.end is not None
    length = decoded.end.astimezone(UTC) - decoded.start.astimezone(UTC)
    assert length == timedelta(minutes=30)


@pytest.mark.parametrize(("decode", "make"), DECODERS)
def test_a_session_that_really_ends_first_is_still_refused(
    decode: Callable[[object, ZoneInfo], records.Slot | records.OpenSpace],
    make: Callable[[str, str], dict[str, object]],
) -> None:
    """A session whose end instant is before its start is refused, on that night too."""
    with pytest.raises(ValueError, match="before it starts"):
        decode(make(*BACKWARDS), ZONE)
