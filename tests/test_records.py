"""Properties of decoding single feed records (``core/records.py``; #150).

The decoding of whole feeds, with named edge cases, is tested in ``test_feed.py``. These
properties call the decoders directly, without the ``machine_tz`` fixture: hypothesis
cannot rerun a function-scoped fixture per example, and the decoders take the zone as an
argument.
"""

import re
from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core import records

ZONE = ZoneInfo("America/Los_Angeles")
SURROGATE = re.compile(r"[\ud800-\udfff]")

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
    assert SURROGATE.sub("\ufffd", text) in strings  # the rest of the text is kept
    assert not any(SURROGATE.search(string) for string in strings)
