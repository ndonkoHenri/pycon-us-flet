"""Tests for the demo videos' trimming: which stretches of a recording a clip keeps."""

from tools.clip_processing import HEAD_STILL, OUTPUT_FPS, _output_times, still_cuts


def test_the_ends_are_trimmed_and_a_long_still_is_shortened() -> None:
    """Maestro's start, a busy host's wait and the end go; a flow's own pause stays."""
    assert still_cuts([10.0, 12.0, 30.0, 31.0], 40.0) == [(8.0, 15.0), (30.0, 33.0)]


def test_a_recording_that_never_changes_keeps_only_its_opening() -> None:
    """With no change to keep, the clip is the opening's hold, not the whole recording."""
    assert still_cuts([], 40.0) == [(0.0, HEAD_STILL)]


def test_each_clip_frame_shows_the_recording_s_time_in_order() -> None:
    """The kept stretches run one after another at the clip's frame rate, nothing doubled."""
    times = _output_times([(1.0, 1.1), (5.0, 5.1)])
    rate = OUTPUT_FPS
    assert times == [1.0 + i / rate for i in range(3)] + [
        5.0 + i / rate for i in range(3)
    ]
