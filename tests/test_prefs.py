"""Tests for the Prefs store: load, save and checked values (STORE-08..10).

SharedPreferences is the in-memory fake from ``tests/fakes.py``; Flet's own type check in
``SharedPreferences.set`` still runs. The OS facts and Developer options are
``test_prefs_values.py``'s.
"""

import json
import logging
from pathlib import Path

import flet as ft
import pytest

from pycon_us.prefs import (
    APPEARANCES,
    HIGH_CONTRAST_SETTINGS,
    START_SCREENS,
    Prefs,
)
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services import pref_keys
from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs


@pytest.fixture
def shared() -> MemoryPrefs:
    """An empty in-memory SharedPreferences."""
    return MemoryPrefs()


@pytest.fixture
def store(shared: MemoryPrefs, tmp_path: Path) -> Storage:
    """The 2026 storage over ``shared`` and a temporary directory."""
    return Storage(prefs=shared, directory=tmp_path, year=2026)


async def loaded(store: Storage) -> Prefs:
    """A new ``Prefs`` loaded from ``store``."""
    prefs = Prefs()
    await prefs.load(store)
    return prefs


# ------------------------------------------------------------------ load


async def test_a_first_launch_reads_every_default(store: Storage) -> None:
    """On a first launch, every preference reads its default; Open Space is hidden."""
    prefs = await loaded(store)
    assert prefs.theme == "system"
    assert prefs.high_contrast == "system"
    assert prefs.onboarded is False
    assert prefs.excluded_tracks == ("Open Space",)  # hidden by default (D-20)
    assert prefs.reminders == ReminderSettings()  # session reminders off (D-275)
    assert prefs.dev == {}
    assert prefs.start_screen == "auto"  # the Lead scanner for a sponsor (D-16)


async def test_load_reads_what_was_stored(store: Storage, shared: MemoryPrefs) -> None:
    """Loading reads back every stored preference, the JSON ones decoded."""
    shared.values.update(
        {
            "pycon.theme": "dark",
            "pycon.high_contrast": "on",
            "pycon.onboarded": True,
            "pycon.excluded_tracks": ["Talk", "Tutorial"],
            "pycon.reminders": '{"session_lead": 10, "primer": "accepted"}',
            "pycon.dev": '{"feed_url": "http://127.0.0.1:8000/feed.json"}',
            "pycon.start_screen": "now",
        }
    )
    prefs = await loaded(store)
    assert prefs.start_screen == "now"
    assert (prefs.theme, prefs.high_contrast, prefs.onboarded) == ("dark", "on", True)
    assert prefs.excluded_tracks == ("Talk", "Tutorial")
    assert prefs.reminders == ReminderSettings(session_lead=10, primer="accepted")
    assert prefs.dev == {"feed_url": "http://127.0.0.1:8000/feed.json"}


async def test_a_stored_empty_track_list_hides_nothing(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A stored empty list of hidden tracks hides nothing, not the default track."""
    shared.values["pycon.excluded_tracks"] = []
    assert (await loaded(store)).excluded_tracks == ()


async def test_reminder_settings_merge_over_their_defaults_on_load(
    store: Storage, shared: MemoryPrefs, caplog: pytest.LogCaptureFixture
) -> None:
    """A stored record with a bad and an unknown key loads its good keys over defaults.

    The bad key reads as its default and both are logged by name (D-120, D-275).
    """
    shared.values["pycon.reminders"] = json.dumps(
        {"session_lead": "ten", "open_space": False, "push": True}
    )
    with caplog.at_level(logging.WARNING):
        prefs = await loaded(store)
    assert prefs.reminders == ReminderSettings(open_space=False)
    assert "session_lead" in caplog.text
    assert "push" in caplog.text


@pytest.mark.parametrize("stored", ["[10]", '"10"', "{not json"])
async def test_a_reminder_record_that_is_no_object_reads_as_the_defaults(
    stored: str, store: Storage, shared: MemoryPrefs
) -> None:
    """A stored reminder value that is not a JSON object loads as the defaults."""
    shared.values["pycon.reminders"] = stored
    assert (await loaded(store)).reminders == ReminderSettings()


@pytest.mark.parametrize(
    ("key", "field", "default"),
    [
        ("pycon.theme", "theme", "system"),
        ("pycon.high_contrast", "high_contrast", "system"),
        ("pycon.start_screen", "start_screen", "auto"),
    ],
)
async def test_an_unknown_setting_value_reads_as_the_default_and_is_logged(
    key: str,
    field: str,
    default: str,
    store: Storage,
    shared: MemoryPrefs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unknown appearance, contrast or start screen value loads as its default.

    Its key is logged.

    The value itself is never logged (D-120).
    """
    shared.values[key] = "sepia"
    with caplog.at_level(logging.WARNING):
        prefs = await loaded(store)
    assert getattr(prefs, field) == default
    assert key in caplog.text
    assert "sepia" not in caplog.text  # the key is logged, never the value (D-120)


async def test_unreadable_preferences_read_as_their_defaults(
    store: Storage, shared: MemoryPrefs
) -> None:
    """When SharedPreferences fails to read, every preference loads as its default."""
    shared.error = TimeoutError()
    prefs = await loaded(store)
    assert (prefs.theme, prefs.excluded_tracks) == ("system", ("Open Space",))


async def test_load_leaves_the_boot_gate_to_its_caller(store: Storage) -> None:
    """Loading leaves ``loaded`` False: its caller opens the boot gate."""
    assert (await loaded(store)).loaded is False


def test_the_first_value_of_each_setting_is_its_storage_default() -> None:
    """The appearance and contrast choices start with "system", their stored default."""
    assert APPEARANCES == ("system", "light", "dark")
    assert APPEARANCES[0] == pref_keys.THEME.default
    assert HIGH_CONTRAST_SETTINGS == ("system", "on", "off")
    assert HIGH_CONTRAST_SETTINGS[0] == pref_keys.HIGH_CONTRAST.default
    assert START_SCREENS == ("auto", "now", "lead")
    assert START_SCREENS[0] == pref_keys.START_SCREEN.default


# ------------------------------------------------------------------ save


async def test_saved_settings_are_shown_and_survive_a_relaunch(
    store: Storage, shared: MemoryPrefs
) -> None:
    """Saved settings apply at once and load again after a relaunch.

    The hidden tracks are stored as a list, for Flutter (F12).
    """
    prefs = await loaded(store)
    saved = await prefs.save(
        store,
        theme="dark",
        high_contrast="off",
        onboarded=True,
        excluded_tracks=(),
        reminders=ReminderSettings(session_lead=5, keynote=False, primer="accepted"),
        dev={"fake_now": "2026-05-15T09:00:00-07:00"},
        start_screen="lead",
    )
    assert saved is True
    assert (prefs.theme, prefs.high_contrast, prefs.excluded_tracks) == (
        "dark",
        "off",
        (),
    )
    assert shared.values["pycon.excluded_tracks"] == []  # a list for Flutter (F12)
    relaunched = await loaded(store)
    assert relaunched.theme == "dark"
    assert relaunched.high_contrast == "off"
    assert relaunched.onboarded is True
    assert relaunched.excluded_tracks == ()
    assert relaunched.reminders == ReminderSettings(
        session_lead=5, keynote=False, primer="accepted"
    )
    assert relaunched.dev == {"fake_now": "2026-05-15T09:00:00-07:00"}
    assert relaunched.start_screen == "lead"


async def test_settings_left_out_are_neither_written_nor_changed(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A save writes and changes only the settings it is given."""
    prefs = await loaded(store)
    await prefs.save(store, theme="light")
    assert set(shared.values) == {"pycon.theme"}
    assert prefs.excluded_tracks == ("Open Space",)


async def test_a_change_that_cannot_be_saved_is_kept_for_the_session(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A change whose write fails returns False, but holds until the app relaunches."""
    prefs = await loaded(store)
    shared.fail_writes = True
    assert await prefs.save(store, theme="dark", onboarded=True) is False
    assert (prefs.theme, prefs.onboarded) == ("dark", True)  # D-120
    assert (
        await loaded(store)
    ).theme == "system"  # lost on relaunch, hence the message


async def test_a_shared_preferences_error_on_save_is_reported_as_not_saved(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A SharedPreferences error on save returns False; the change holds in memory."""
    prefs = await loaded(store)
    shared.error = RuntimeError("client error")
    assert await prefs.save(store, theme="light") is False
    assert prefs.theme == "light"


async def test_reminder_settings_are_stored_as_one_json_object(
    store: Storage, shared: MemoryPrefs
) -> None:
    """Saved reminder settings are written whole, as a JSON object of every field."""
    prefs = await loaded(store)
    settings = ReminderSettings(session_lead=15, primer="not_now")
    assert await prefs.save(store, reminders=settings) is True
    assert json.loads(shared.values["pycon.reminders"]) == settings.to_stored()
    assert prefs.reminders == settings


async def test_reminder_settings_that_cannot_be_saved_hold_for_the_session(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A reminder change whose write fails returns False and holds until a relaunch."""
    prefs = await loaded(store)
    shared.fail_writes = True
    settings = ReminderSettings(session_lead=10, primer="accepted")
    assert await prefs.save(store, reminders=settings) is False  # D-120
    assert prefs.reminders == settings
    shared.fail_writes = False
    assert (await loaded(store)).reminders == ReminderSettings()


async def test_one_failed_write_still_writes_the_others(
    store: Storage, shared: MemoryPrefs
) -> None:
    """One failed write makes the save return False; the others are still written."""
    prefs = await loaded(store)

    async def fail_theme_only(key: str, value: object) -> bool:
        if key == "pycon.theme":
            return False
        shared.values[key] = value
        return True

    shared.set = fail_theme_only  # type: ignore[method-assign]
    assert await prefs.save(store, theme="dark", onboarded=True) is False
    assert shared.values == {"pycon.onboarded": True}


@pytest.mark.parametrize(
    "change",
    [
        {"theme": "sepia"},
        {"high_contrast": "auto"},
        {"theme": "Dark"},
        {"start_screen": "schedule"},
    ],
)
async def test_save_rejects_an_unknown_setting_value_and_changes_nothing(
    change: dict[str, str], store: Storage, shared: MemoryPrefs
) -> None:
    """A save with an unknown appearance, contrast or start screen raises, changes nothing."""
    prefs = await loaded(store)
    with pytest.raises(ValueError, match="must be one of"):
        await prefs.save(store, onboarded=True, **change)  # type: ignore[arg-type]
    assert shared.values == {}
    assert prefs.onboarded is False


async def test_a_save_notifies_subscribers_of_each_changed_field(
    store: Storage,
) -> None:
    """A save notifies subscribers once per changed field, in order."""
    prefs = await loaded(store)
    changes: list[str | None] = []

    def listen(_sender: object, field: str | None) -> None:
        changes.append(field)

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listen)  # held weakly: a local function, not a lambda
    await prefs.save(store, theme="dark", excluded_tracks=("Talk",))
    assert changes == ["theme", "excluded_tracks"]


async def test_reduced_motion_is_never_stored(
    store: Storage, shared: MemoryPrefs
) -> None:
    """A save never writes reduced motion, so a relaunch reads it as off."""
    prefs = await loaded(store)
    prefs.reduce_motion = True  # what read_accessibility() writes
    await prefs.save(store, theme="dark")
    # A device fact, read at start and on resume (F13), not a setting (D-34).
    assert not any("motion" in key for key in shared.values)
    assert not (await loaded(store)).reduce_motion
