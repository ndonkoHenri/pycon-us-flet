"""Tests for the Prefs store: load, save, checked values and the OS facts (STORE-08..10).

SharedPreferences is the in-memory fake from ``tests/fakes.py``; Flet's own type check in
``SharedPreferences.set`` still runs.
"""

import logging
from pathlib import Path

import flet as ft
import pytest

from pycon_us.prefs import APPEARANCES, HIGH_CONTRAST_SETTINGS, Prefs
from pycon_us.services import storage
from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs


@pytest.fixture
def shared() -> MemoryPrefs:
    return MemoryPrefs()


@pytest.fixture
def store(shared: MemoryPrefs, tmp_path: Path) -> Storage:
    return Storage(prefs=shared, directory=tmp_path, year=2026)


async def loaded(store: Storage) -> Prefs:
    prefs = Prefs()
    await prefs.load(store)
    return prefs


# ------------------------------------------------------------------ load


async def test_a_first_launch_reads_every_default(store: Storage) -> None:
    prefs = await loaded(store)
    assert prefs.theme == "system"
    assert prefs.high_contrast == "system"
    assert prefs.onboarded is False
    assert prefs.excluded_tracks == ("Open Space",)  # hidden by default (D-20)
    assert prefs.reminders == {}
    assert prefs.dev == {}


async def test_load_reads_what_was_stored(store: Storage, shared: MemoryPrefs) -> None:
    shared.values.update(
        {
            "pycon.theme": "dark",
            "pycon.high_contrast": "on",
            "pycon.onboarded": True,
            "pycon.excluded_tracks": ["Talk", "Tutorial"],
            "pycon.reminders": '{"session_reminders": 10}',
            "pycon.dev": '{"feed_url": "http://127.0.0.1:8000/feed.json"}',
        }
    )
    prefs = await loaded(store)
    assert (prefs.theme, prefs.high_contrast, prefs.onboarded) == ("dark", "on", True)
    assert prefs.excluded_tracks == ("Talk", "Tutorial")
    assert prefs.reminders == {"session_reminders": 10}
    assert prefs.dev == {"feed_url": "http://127.0.0.1:8000/feed.json"}


async def test_a_stored_empty_track_list_hides_nothing(
    store: Storage, shared: MemoryPrefs
) -> None:
    shared.values["pycon.excluded_tracks"] = []
    assert (await loaded(store)).excluded_tracks == ()


@pytest.mark.parametrize(
    ("key", "field"),
    [("pycon.theme", "theme"), ("pycon.high_contrast", "high_contrast")],
)
async def test_an_unknown_setting_value_reads_as_the_default_and_is_logged(
    key: str,
    field: str,
    store: Storage,
    shared: MemoryPrefs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    shared.values[key] = "sepia"
    with caplog.at_level(logging.WARNING):
        prefs = await loaded(store)
    assert getattr(prefs, field) == "system"
    assert key in caplog.text
    assert "sepia" not in caplog.text  # the key is logged, never the value (D-120)


async def test_unreadable_preferences_read_as_their_defaults(
    store: Storage, shared: MemoryPrefs
) -> None:
    shared.error = TimeoutError()
    prefs = await loaded(store)
    assert (prefs.theme, prefs.excluded_tracks) == ("system", ("Open Space",))


async def test_load_leaves_the_boot_gate_to_its_caller(store: Storage) -> None:
    assert (await loaded(store)).loaded is False


def test_the_first_value_of_each_setting_is_its_storage_default() -> None:
    assert APPEARANCES == ("system", "light", "dark")
    assert APPEARANCES[0] == storage.THEME.default
    assert HIGH_CONTRAST_SETTINGS == ("system", "on", "off")
    assert HIGH_CONTRAST_SETTINGS[0] == storage.HIGH_CONTRAST.default


# ------------------------------------------------------------------ save


async def test_saved_settings_are_shown_and_survive_a_relaunch(
    store: Storage, shared: MemoryPrefs
) -> None:
    prefs = await loaded(store)
    saved = await prefs.save(
        store,
        theme="dark",
        high_contrast="off",
        onboarded=True,
        excluded_tracks=(),
        reminders={"session_reminders": 5},
        dev={"fake_now": "2026-05-15T09:00:00-07:00"},
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
    assert relaunched.reminders == {"session_reminders": 5}
    assert relaunched.dev == {"fake_now": "2026-05-15T09:00:00-07:00"}


async def test_settings_left_out_are_neither_written_nor_changed(
    store: Storage, shared: MemoryPrefs
) -> None:
    prefs = await loaded(store)
    await prefs.save(store, theme="light")
    assert set(shared.values) == {"pycon.theme"}
    assert prefs.excluded_tracks == ("Open Space",)


async def test_a_change_that_cannot_be_saved_is_kept_for_the_session(
    store: Storage, shared: MemoryPrefs
) -> None:
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
    prefs = await loaded(store)
    shared.error = RuntimeError("client error")
    assert await prefs.save(store, theme="light") is False
    assert prefs.theme == "light"


async def test_one_failed_write_still_writes_the_others(
    store: Storage, shared: MemoryPrefs
) -> None:
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
    "change", [{"theme": "sepia"}, {"high_contrast": "auto"}, {"theme": "Dark"}]
)
async def test_save_rejects_an_unknown_setting_value_and_changes_nothing(
    change: dict[str, str], store: Storage, shared: MemoryPrefs
) -> None:
    prefs = await loaded(store)
    with pytest.raises(ValueError, match="must be one of"):
        await prefs.save(store, onboarded=True, **change)  # type: ignore[arg-type]
    assert shared.values == {}
    assert prefs.onboarded is False


async def test_a_save_notifies_subscribers_of_each_changed_field(
    store: Storage,
) -> None:
    prefs = await loaded(store)
    changes: list[str | None] = []

    def listen(_sender: object, field: str | None) -> None:
        changes.append(field)

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listen)  # held weakly: a local function, not a lambda
    await prefs.save(store, theme="dark", excluded_tracks=("Talk",))
    assert changes == ["theme", "excluded_tracks"]


# ------------------------------------------------------------------ resolved values


@pytest.mark.parametrize(
    ("theme", "os_dark", "dark"),
    [
        ("system", False, False),
        ("system", True, True),
        ("light", True, False),
        ("dark", False, True),
    ],
)
def test_dark_follows_the_os_only_under_system(
    theme: str, os_dark: bool, dark: bool
) -> None:
    assert Prefs(theme=theme, os_dark=os_dark).dark is dark  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("setting", "os_flag", "on"),
    [
        ("system", False, False),
        ("system", True, True),
        ("on", False, True),
        ("off", True, False),
    ],
)
def test_high_contrast_follows_the_os_flag_only_under_system(
    setting: str, os_flag: bool, on: bool
) -> None:
    prefs = Prefs(high_contrast=setting, os_high_contrast=os_flag)  # type: ignore[arg-type]
    assert prefs.high_contrast_on is on


@pytest.mark.parametrize(("reduce_motion", "ms"), [(False, 400), (True, 0)])
def test_an_animation_lasts_its_duration_unless_the_os_asks_for_less_motion(
    reduce_motion: bool, ms: int
) -> None:
    assert Prefs(reduce_motion=reduce_motion).motion_ms(400) == ms  # D-34


async def test_reduced_motion_is_never_stored(
    store: Storage, shared: MemoryPrefs
) -> None:
    prefs = await loaded(store)
    prefs.reduce_motion = True  # what read_accessibility() writes
    await prefs.save(store, theme="dark")
    # A device fact, read at start and on resume (F13), not a setting (D-34).
    assert not any("motion" in key for key in shared.values)
    assert not (await loaded(store)).reduce_motion
