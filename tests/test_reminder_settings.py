"""Tests for the reminder settings record: defaults, the merge over them, and checks (D-275)."""

import itertools
import json
import logging
from dataclasses import fields, replace
from typing import Any

import pytest

from pycon_us.reminder_settings import (
    PRIMER_ANSWERS,
    SESSION_LEADS,
    ReminderSettings,
)

DEFAULTS = ReminderSettings()
"""The record a fresh install has."""


def test_the_defaults_are_session_reminders_off_and_every_moment_on() -> None:
    """A fresh record has no session reminder, every conference moment on, no primer."""
    assert DEFAULTS.to_stored() == {
        "session_lead": 0,
        "lightning": True,
        "open_space": True,
        "keynote": True,
        "primer": "unasked",
    }


def test_the_choices_are_the_leads_and_answers_the_settings_offer() -> None:
    """Leads are off, 5, 10 and 15 minutes; the primer is unasked, accepted or not now."""
    assert SESSION_LEADS == (0, 5, 10, 15)
    assert PRIMER_ANSWERS == ("unasked", "accepted", "not_now")
    assert (DEFAULTS.session_lead, DEFAULTS.primer) == (
        SESSION_LEADS[0],
        PRIMER_ANSWERS[0],
    )


def test_an_absent_record_reads_as_the_defaults_without_a_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty stored object, a first launch, gives the defaults and logs nothing."""
    with caplog.at_level(logging.WARNING):
        assert ReminderSettings.from_stored({}) == DEFAULTS
    assert caplog.records == []


def test_missing_keys_read_as_their_defaults_and_given_ones_are_kept() -> None:
    """A record with some keys keeps them and takes the defaults for the others."""
    settings = ReminderSettings.from_stored({"session_lead": 15, "keynote": False})
    assert settings == replace(DEFAULTS, session_lead=15, keynote=False)


def test_every_record_survives_its_stored_form() -> None:
    """Every combination of values reads back unchanged from its JSON form."""
    for lead, lightning, open_space, keynote, primer in itertools.product(
        SESSION_LEADS, (True, False), (True, False), (True, False), PRIMER_ANSWERS
    ):
        settings = ReminderSettings(lead, lightning, open_space, keynote, primer)
        stored = json.loads(json.dumps(settings.to_stored()))  # as Storage keeps it
        assert ReminderSettings.from_stored(stored) == settings


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("session_lead", 20),  # not an offered lead
        ("session_lead", "10"),
        ("session_lead", 10.0),
        ("session_lead", True),  # a bool is an int to Python, never a lead
        ("session_lead", None),
        ("lightning", "yes"),
        ("open_space", 1),  # 1 == True, but not a bool
        ("keynote", None),
        ("primer", "later"),
        ("primer", False),
    ],
)
def test_a_badly_typed_key_reads_as_its_default_and_is_logged_by_name(
    key: str, value: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A key with a value outside its set reads as its default; the others are kept.

    The log names the key, never the value (D-120).
    """
    stored = {"session_lead": 5, "primer": "accepted", "lightning": False} | {
        key: value
    }
    with caplog.at_level(logging.WARNING):
        settings = ReminderSettings.from_stored(stored)
    kept = {name: stored[name] for name in stored if name != key}
    assert settings == replace(DEFAULTS, **kept)
    assert [record.getMessage() for record in caplog.records] == [
        f"Preference pycon.reminders: read as their defaults: {key}"
    ]


def test_unknown_keys_are_dropped_and_logged_in_one_line_with_bad_ones(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown keys are dropped; one warning names them with the defaulted keys."""
    stored = {"session_reminders": 10, "push": True, "primer": 3, "keynote": False}
    with caplog.at_level(logging.WARNING):
        settings = ReminderSettings.from_stored(stored)
    assert settings == replace(DEFAULTS, keynote=False)
    line = (
        "Preference pycon.reminders: read as their defaults: primer; "
        "unknown keys dropped: push, session_reminders"
    )
    assert [record.getMessage() for record in caplog.records] == [line]  # keys only


@pytest.mark.parametrize(
    "change",
    [
        {"session_lead": 30},
        {"session_lead": True},
        {"lightning": "on"},
        {"primer": "denied"},
    ],
)
def test_building_a_record_outside_its_choices_raises(change: dict[str, Any]) -> None:
    """A record with a value outside its field's set is refused, so it is never saved."""
    with pytest.raises(ValueError, match="must be one of"):
        ReminderSettings(**change)
    with pytest.raises(ValueError, match="must be one of"):
        replace(DEFAULTS, **change)


def test_the_stored_form_names_every_field() -> None:
    """The stored object has one key per field, so a new field is stored too."""
    assert set(DEFAULTS.to_stored()) == {field.name for field in fields(DEFAULTS)}
