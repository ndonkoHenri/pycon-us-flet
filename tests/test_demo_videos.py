"""Tests for the demo videos' tool: the scenes it stores and the stretches it keeps."""

import json
from pathlib import Path

from pycon_us.dev_options import DEV_FAKE_NOW, DEV_MOCK_API_URL, DEV_UNLOCKED
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services.pref_keys import DEV, ONBOARDED, REMINDERS
from tools import demo_videos
from tools.demo_videos import (
    CLIPS,
    FLOWS,
    _output_times,
    merged_prefs,
    scene_prefs,
    still_cuts,
)

MAESTRO = Path(demo_videos.__file__).resolve().parents[1] / "maestro"


def test_a_scene_never_stores_the_developer_unlock() -> None:
    """Locked, neither More nor About this app has a Developer row, in any scene."""
    for mock_url in (None, "http://localhost:8100"):
        dev = json.loads(scene_prefs(mock_url)[f"flutter.{DEV.key}"])
        assert DEV_UNLOCKED not in dev


def test_only_the_staff_scene_stores_the_mock_s_url() -> None:
    """A scene with no mock shows no sign-in row; its clock is set either way."""
    plain = json.loads(scene_prefs(None)[f"flutter.{DEV.key}"])
    assert DEV_MOCK_API_URL not in plain
    assert plain[DEV_FAKE_NOW] == demo_videos.FAKE_NOW
    dev = json.loads(scene_prefs("http://localhost:8100")[f"flutter.{DEV.key}"])
    assert dev[DEV_MOCK_API_URL] == "http://localhost:8100"
    assert dev[DEV_FAKE_NOW] == demo_videos.FAKE_NOW


def test_a_scene_s_keys_and_values_are_the_ones_the_app_reads() -> None:
    """A renamed preference fails here, rather than filming Welcome or the real clock."""
    scene = scene_prefs(None)
    assert set(scene) == {f"flutter.{p.key}" for p in (ONBOARDED, REMINDERS, DEV)}
    stored = json.loads(scene[f"flutter.{REMINDERS.key}"])
    assert ReminderSettings.from_stored(stored).primer == "not_now"


def test_a_scene_replaces_the_app_s_keys_and_keeps_the_os_s() -> None:
    """The stars of an earlier take go; what the plugins keep there stays."""
    stored = {"flutter.pycon.2026.favorites": ["153"], "callback_handle": 1}
    merged = merged_prefs(stored, scene_prefs(None))
    assert "flutter.pycon.2026.favorites" not in merged
    assert merged["callback_handle"] == 1
    assert merged["flutter.pycon.onboarded"] is True


def test_the_ends_are_trimmed_and_a_long_still_is_shortened() -> None:
    """Maestro's start, a busy host's wait and the end go; a flow's own pause stays."""
    assert still_cuts([10.0, 12.0, 30.0, 31.0], 40.0) == [(8.0, 15.0), (30.0, 33.0)]


def test_a_recording_that_never_changes_keeps_only_its_opening() -> None:
    """With no change to keep, the clip is the opening's hold, not the whole recording."""
    assert still_cuts([], 40.0) == [(0.0, demo_videos.HEAD_STILL)]


def test_every_clip_s_flows_exist_and_stay_out_of_the_test_workspace() -> None:
    """A retake finds its flows; `maestro test maestro` never films a clip."""
    for clip in CLIPS:
        for name in (*clip.flows, *([clip.setup] if clip.setup else [])):
            assert (FLOWS / name).is_file()
    config = (MAESTRO / "config.yaml").read_text()
    globs = [line for line in config.splitlines() if line.startswith("  - ")]
    assert globs and not any("demo" in line for line in globs)


def test_each_clip_frame_shows_the_recording_s_time_in_order() -> None:
    """The kept stretches run one after another at the clip's frame rate, nothing doubled."""
    times = _output_times([(1.0, 1.1), (5.0, 5.1)])
    rate = demo_videos.OUTPUT_FPS
    assert times == [1.0 + i / rate for i in range(3)] + [
        5.0 + i / rate for i in range(3)
    ]


def test_the_staff_clip_says_mock_data_in_its_name() -> None:
    """Only that clip uses the mock, and a viewer can tell so from the file's name."""
    assert [c.name for c in CLIPS if c.mock] == ["staff-tools-mock-data"]


def test_no_demo_flow_goes_near_the_developer_screen() -> None:
    """Only a check that it's absent may name it: a frame would reach people outside."""
    for flow in FLOWS.rglob("*.yaml"):
        for line in flow.read_text().splitlines():
            if line.lstrip().startswith("#") or "assertNotVisible" in line:
                continue
            lowered = line.lower()
            assert "developer" not in lowered, line
            assert "about_app" not in lowered, line
            assert "about this app" not in lowered, line


def test_the_status_bar_starts_at_the_clock_s_nine_forty_one() -> None:
    """The first frame of a scene reads 9:41, which the stored fake clock says."""
    assert demo_videos.fake_minute(0) == "9:41"
    assert demo_videos.fake_minute(-5) == "9:41"  # before the clock starts


def test_the_status_bar_follows_the_fake_clock_s_minute() -> None:
    """A clip that outlasts a minute shows the minute the app's "Now" line shows."""
    assert demo_videos.fake_minute(59.9) == "9:41"
    assert demo_videos.fake_minute(60) == "9:42"
    assert demo_videos.fake_minute(190) == "9:44"


def test_the_next_change_is_the_seconds_left_in_the_minute() -> None:
    """The follower wakes at each minute's end, not every second."""
    assert demo_videos.seconds_to_next_minute(0) == 60
    assert demo_videos.seconds_to_next_minute(45) == 15
    assert demo_videos.seconds_to_next_minute(60) == 60
