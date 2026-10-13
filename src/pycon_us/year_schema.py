"""The schema half of the year-data loader: TOML tables into frozen dataclasses (D-45).

``read_table()`` reads one file with ``tomllib``; ``build()`` turns a table into a
dataclass, recursively, checking key names and value types against the dataclass's own
fields, so the dataclasses in ``config`` are the schema (architecture §8.2). Nothing here
knows about conferences: the rules a year's entries must follow, and the dataclasses
themselves, are ``config``'s. Every failure is a ``YearDataError`` that names the file,
the key and the problem.
"""

import dataclasses
import tomllib
import types
import typing
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

_TYPE_NAMES = {
    str: "a string",
    int: "an integer",
    bool: "true or false",
    date: "a date",
    datetime: "a date and time",
}


class YearDataError(ValueError):
    """A year data file is missing or invalid; the message names the file, key and problem."""


def read_table(path: Path, file: str) -> dict[str, object]:
    """Read the TOML file at ``path`` into its top-level table.

    Args:
        path: The file to read.
        file: Its name in error messages (``2026/conference.toml``).

    Returns:
        The file's top-level table.

    Raises:
        YearDataError: The file is missing or is not valid TOML.
    """
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except FileNotFoundError:
        raise YearDataError(f"{file}: file not found") from None
    except tomllib.TOMLDecodeError as error:
        raise YearDataError(f"{file}: invalid TOML: {error}") from None


def build[T: DataclassInstance](
    cls: type[T], raw: object, file: str, key: str = ""
) -> T:
    """Build dataclass ``cls`` from a TOML table, checking key names and value types.

    Args:
        cls: The dataclass; its fields name the keys, their annotations the types. A
            table is a dataclass, and an array of tables a ``tuple`` of one, each
            built in turn.
        raw: The table.
        file: The file's name in error messages.
        key: Where the table is in the file (``tracks[8]``); empty for the top level.

    Returns:
        The dataclass.

    Raises:
        YearDataError: A key is unknown or missing, or a value has the wrong type.
    """
    if not isinstance(raw, dict):
        raise YearDataError(f"{file}: {key}: expected a table, got {raw!r}")
    fields = {field.name: field for field in dataclasses.fields(cls)}
    prefix = f"{key}." if key else ""
    if unknown := sorted(raw.keys() - fields.keys()):
        raise YearDataError(f"{file}: {prefix}{unknown[0]}: unknown key")
    required = [
        name
        for name, field in fields.items()
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
    ]
    if missing := [name for name in required if name not in raw]:
        raise YearDataError(f"{file}: {prefix}{missing[0]}: missing key")
    hints = typing.get_type_hints(cls)
    values = {
        name: _value(hints[name], value, file, prefix + name)
        for name, value in raw.items()
    }
    return cls(**values)


def _value(expected: object, value: object, file: str, key: str) -> object:
    if isinstance(expected, types.UnionType):  # an optional key, `X | None`
        # TOML has no null: a key that is present holds an X.
        (expected,) = (
            arg for arg in typing.get_args(expected) if arg is not type(None)
        )
    if dataclasses.is_dataclass(expected):  # a table of its own, `[lightning_talks]`
        return build(cast("type[DataclassInstance]", expected), value, file, key)
    if expected == tuple[str, ...]:  # an array of strings
        if not isinstance(value, list) or not all(type(v) is str for v in value):
            raise YearDataError(
                f"{file}: {key}: expected an array of strings, got {value!r}"
            )
        return tuple(value)
    if typing.get_origin(expected) is tuple:  # an array of tables
        item_cls = typing.get_args(expected)[0]
        if not isinstance(value, list):
            raise YearDataError(
                f"{file}: {key}: expected an array of tables, got {value!r}"
            )
        return tuple(
            build(item_cls, item, file, f"{key}[{index}]")
            for index, item in enumerate(value)
        )
    # type() rather than isinstance(): a bool is not an integer, and a datetime is not a date.
    if type(value) is not expected:
        raise YearDataError(
            f"{file}: {key}: expected {_TYPE_NAMES[expected]}, got {value!r}"
        )
    return value
