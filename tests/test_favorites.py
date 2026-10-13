"""Tests for the Favorites store: persistence, years, notifications and Undo (STORE-02).

SharedPreferences is the in-memory fake from ``tests/fakes.py``; Flet's own type check in
``SharedPreferences.set`` still runs, so a value it would refuse fails here too (F12).
"""

import asyncio
import logging
from pathlib import Path

import flet as ft
import pytest

from pycon_us.favorites import Change, Favorites
from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs


@pytest.fixture
def shared() -> MemoryPrefs:
    return MemoryPrefs()


@pytest.fixture
def store(shared: MemoryPrefs, tmp_path: Path) -> Storage:
    return Storage(prefs=shared, directory=tmp_path, year=2026)


async def loaded(store: Storage) -> Favorites:
    favorites = Favorites()
    await favorites.load(store)
    return favorites


class Notifications:
    """Records the fields a store notifies; the test holds it, as stores hold listeners
    weakly (a local function would be collected when the helper returns)."""

    def __init__(self, favorites: Favorites) -> None:
        self.seen: list[str | None] = []
        assert isinstance(favorites, ft.Observable)
        favorites.subscribe(self)

    def __call__(self, _sender: object, field: str | None) -> None:
        self.seen.append(field)


# ------------------------------------------------------------------ load and persistence


async def test_a_first_launch_has_no_favourites(store: Storage) -> None:
    favorites = await loaded(store)
    assert favorites.ids == frozenset()
    assert favorites.loaded  # an empty list, not an unread one: My schedule is empty


async def test_favourites_survive_a_relaunch(
    store: Storage, shared: MemoryPrefs
) -> None:
    favorites = await loaded(store)
    await favorites.toggle(store, "42")
    await favorites.add_many(store, ["poster-detail-7", "9042"])
    relaunched = await loaded(store)
    assert relaunched.ids == {"42", "poster-detail-7", "9042"}
    # A list for Flutter (F12), sorted so the same set is always the same value.
    assert shared.values["pycon.2026.favorites"] == ["42", "9042", "poster-detail-7"]


async def test_a_2026_favourite_never_marks_a_2027_session(
    shared: MemoryPrefs, tmp_path: Path
) -> None:
    store_2026 = Storage(prefs=shared, directory=tmp_path, year=2026)
    store_2027 = Storage(prefs=shared, directory=tmp_path, year=2027)
    await (await loaded(store_2026)).toggle(store_2026, "42")
    favorites_2027 = await loaded(store_2027)
    assert "42" not in favorites_2027.ids  # ids are unique only within a year (D-48)
    await favorites_2027.toggle(store_2027, "17")
    assert (await loaded(store_2026)).ids == {"42"}
    assert set(shared.values) == {"pycon.2026.favorites", "pycon.2027.favorites"}


async def test_unreadable_favourites_read_as_none_and_are_logged(
    store: Storage, shared: MemoryPrefs, caplog: pytest.LogCaptureFixture
) -> None:
    shared.values["pycon.2026.favorites"] = "42"  # not a list[str]
    with caplog.at_level(logging.WARNING):
        favorites = await loaded(store)
    assert favorites.ids == frozenset()
    assert "pycon.2026.favorites" in caplog.text


async def test_a_change_that_cannot_be_saved_is_kept_for_the_session(
    store: Storage, shared: MemoryPrefs
) -> None:
    favorites = await loaded(store)
    shared.fail_writes = True
    change = await favorites.toggle(store, "42")
    assert change == Change(added=frozenset({"42"}), saved=False)
    assert favorites.ids == {"42"}  # D-120: the caller says it was not saved
    assert (await loaded(store)).ids == frozenset()  # lost on relaunch


@pytest.mark.parametrize(
    "error", [TimeoutError(), RuntimeError("client error")], ids=["timeout", "client"]
)
async def test_a_failed_read_never_writes_over_the_saved_favourites(
    error: Exception,
    store: Storage,
    shared: MemoryPrefs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    shared.values["pycon.2026.favorites"] = ["17", "42"]
    shared.error = error
    with caplog.at_level(logging.WARNING):
        favorites = await loaded(store)
    assert favorites.ids == frozenset()
    assert not favorites.loaded  # My schedule says it can't open, not "Nothing saved"
    assert "pycon.2026.favorites" in caplog.text
    shared.error = None  # SharedPreferences works again, but the read was lost
    change = await favorites.toggle(store, "99")
    assert change == Change(added=frozenset({"99"}), saved=False)  # "Couldn't save"
    assert favorites.ids == {"99"}  # shown for the session
    assert shared.values["pycon.2026.favorites"] == ["17", "42"]  # never overwritten


async def test_a_store_that_was_never_read_never_writes(
    store: Storage, shared: MemoryPrefs
) -> None:
    # What a start that broke before the favourites' read leaves (D-161).
    shared.values["pycon.2026.favorites"] = ["17", "42"]
    favorites = Favorites()
    change = await favorites.toggle(store, "99")
    assert change == Change(added=frozenset({"99"}), saved=False)
    assert favorites.ids == {"99"}
    assert shared.values["pycon.2026.favorites"] == ["17", "42"]


# ------------------------------------------------------------------ toggle


async def test_a_toggle_saves_then_removes_a_session(store: Storage) -> None:
    favorites = await loaded(store)
    assert await favorites.toggle(store, "42") == Change(added=frozenset({"42"}))
    assert favorites.ids == {"42"}
    assert await favorites.toggle(store, "42") == Change(removed=frozenset({"42"}))
    assert favorites.ids == frozenset()


async def test_a_toggle_notifies_exactly_once(store: Storage) -> None:
    favorites = await loaded(store)
    notified = Notifications(favorites)
    await favorites.toggle(store, "42")
    assert notified.seen == ["ids"]
    await favorites.toggle(store, "42")
    assert notified.seen == ["ids", "ids"]


async def test_the_star_changes_before_the_write_answers(
    store: Storage, shared: MemoryPrefs
) -> None:
    favorites = await loaded(store)
    writing, answer = asyncio.Event(), asyncio.Event()

    async def slow_set(key: str, value: object) -> bool:
        writing.set()
        await answer.wait()
        shared.values[key] = value
        return True

    shared.set = slow_set  # type: ignore[method-assign]
    toggle = asyncio.create_task(favorites.toggle(store, "42"))
    await writing.wait()
    assert favorites.ids == {"42"}  # shown without a SharedPreferences round trip
    answer.set()
    assert (await toggle).saved


async def test_two_quick_taps_keep_both_sessions(
    store: Storage, shared: MemoryPrefs
) -> None:
    favorites = await loaded(store)

    async def slow_set(key: str, value: object) -> bool:
        await asyncio.sleep(0.01)  # both taps land while the first write is out
        shared.values[key] = value
        return True

    shared.set = slow_set  # type: ignore[method-assign]
    await asyncio.gather(favorites.toggle(store, "42"), favorites.toggle(store, "17"))
    assert favorites.ids == {"42", "17"}
    assert (await loaded(store)).ids == {"42", "17"}


# ------------------------------------------------------------------ add_many and remove_many


async def test_add_many_reports_only_the_sessions_it_saved(store: Storage) -> None:
    favorites = await loaded(store)
    await favorites.toggle(store, "42")
    notified = Notifications(favorites)
    change = await favorites.add_many(store, ["42", "17", "18"])
    # "Added 2 sessions": the one saved before is neither counted nor undone.
    assert change == Change(added=frozenset({"17", "18"}))
    assert favorites.ids == {"42", "17", "18"}
    assert notified.seen == ["ids"]  # one notification for the whole track


async def test_remove_many_reports_only_the_sessions_it_removed(store: Storage) -> None:
    favorites = await loaded(store)
    await favorites.add_many(store, ["42", "17"])
    change = await favorites.remove_many(store, ["17", "99"])
    assert change == Change(removed=frozenset({"17"}))
    assert favorites.ids == {"42"}
    assert (await loaded(store)).ids == {"42"}


async def test_an_edit_that_changes_nothing_neither_notifies_nor_writes(
    store: Storage, shared: MemoryPrefs
) -> None:
    favorites = await loaded(store)
    await favorites.add_many(store, ["42"])
    shared.values.clear()
    notified = Notifications(favorites)
    assert await favorites.add_many(store, ["42"]) == Change()
    assert await favorites.remove_many(store, ["17"]) == Change()
    assert await favorites.add_many(store, []) == Change()
    assert notified.seen == []
    assert shared.values == {}


@pytest.mark.parametrize("method", ["add_many", "remove_many"])
async def test_one_id_string_is_refused_rather_than_split_into_characters(
    method: str, store: Storage
) -> None:
    favorites = await loaded(store)
    with pytest.raises(TypeError, match="collection of session ids"):
        await getattr(favorites, method)(store, "42")
    assert favorites.ids == frozenset()


# ------------------------------------------------------------------ Undo


async def test_undo_brings_back_a_removed_session(store: Storage) -> None:
    favorites = await loaded(store)
    await favorites.toggle(store, "42")
    removal = await favorites.toggle(store, "42")
    notified = Notifications(favorites)
    assert await favorites.undo(store, removal) == Change(added=frozenset({"42"}))
    assert favorites.ids == {"42"}
    assert notified.seen == ["ids"]
    assert (await loaded(store)).ids == {"42"}


async def test_undo_of_add_many_keeps_what_was_saved_before(store: Storage) -> None:
    favorites = await loaded(store)
    await favorites.toggle(store, "42")
    added = await favorites.add_many(store, ["42", "17", "18"])
    await favorites.undo(store, added)
    assert favorites.ids == {"42"}


async def test_undo_of_remove_many_restores_every_removed_session(
    store: Storage,
) -> None:
    favorites = await loaded(store)
    await favorites.add_many(store, ["42", "17", "18"])
    removed = await favorites.remove_many(store, ["17", "18"])
    await favorites.undo(store, removed)
    assert favorites.ids == {"42", "17", "18"}


async def test_an_undo_can_itself_be_undone(store: Storage) -> None:
    favorites = await loaded(store)
    removal = await favorites.toggle(store, "42")  # nothing saved: this adds
    undo = await favorites.undo(store, removal)
    assert favorites.ids == frozenset()
    await favorites.undo(store, undo)
    assert favorites.ids == {"42"}


async def test_undo_after_the_user_changed_the_same_session_does_nothing_twice(
    store: Storage,
) -> None:
    favorites = await loaded(store)
    await favorites.toggle(store, "42")
    removal = await favorites.toggle(store, "42")
    await favorites.toggle(store, "42")  # saved again before tapping Undo
    notified = Notifications(favorites)
    assert await favorites.undo(store, removal) == Change()
    assert favorites.ids == {"42"}
    assert notified.seen == []


async def test_reset_forgets_every_saved_session_without_writing(
    store: Storage, shared: MemoryPrefs
) -> None:
    favorites = await loaded(store)
    await favorites.add_many(store, ["1", "2"])
    shared.values.clear()  # Reset app removed the stored list
    notified = Notifications(favorites)
    favorites.reset()
    assert favorites.ids == frozenset()
    assert notified.seen == ["ids"]  # the lists show it at once
    assert shared.values == {}  # nothing written back
    assert favorites.loaded is True  # the next star saves as usual
