"""Tests for the demo videos' tool: the scenes it stores and the stretches it keeps."""

import json
from pathlib import Path

from pycon_us.dev_options import DEV_UNLOCKED
from tools import demo_videos
from tools.demo_videos import (
    CLIPS,
    FLOWS,
    merged_prefs,
    scene_prefs,
    still_cuts,
)

MAESTRO = Path(demo_videos.__file__).resolve().parents[1] / "maestro"


def test_a_scene_never_stores_the_developer_unlock() -> None:
    """Locked, neither More nor About this app has a Developer row, in any scene."""
    for mock_url in (None, "http://localhost:8100"):
        dev = json.loads(scene_prefs(mock_url)["flutter.pycon.dev"])
        assert DEV_UNLOCKED not in dev


def test_only_the_staff_scene_stores_the_mock_s_url() -> None:
    """A scene with no mock shows no sign-in row; its clock is set either way."""
    assert "mock_api_url" not in json.loads(scene_prefs(None)["flutter.pycon.dev"])
    dev = json.loads(scene_prefs("http://localhost:8100")["flutter.pycon.dev"])
    assert dev["mock_api_url"] == "http://localhost:8100"
    assert dev["fake_now"] == demo_videos.FAKE_NOW


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
    assert "demo" not in (MAESTRO / "config.yaml").read_text()


def test_the_staff_clip_says_mock_data_in_its_name() -> None:
    """Only that clip uses the mock, and a viewer can tell so from the file's name."""
    assert [c.name for c in CLIPS if c.mock] == ["staff-tools-mock-data"]


def test_no_demo_flow_goes_near_the_developer_screen() -> None:
    """No flow opens it or taps its rows: a frame of it would reach people outside."""
    for flow in FLOWS.rglob("*.yaml"):
        text = flow.read_text()
        assert "open_developer" not in text
        assert "developer." not in text
        assert "about_app" not in text
