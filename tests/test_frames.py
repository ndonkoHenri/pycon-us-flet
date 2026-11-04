"""Tests for `tools/frames.py`'s reading of a pixel's colours, with no video reader."""

from tools.frames import colour_changes, hex_colour, pair

PURPLE = (0x68, 0x05, 0x79)
SHIFTED = (0x72, 0x00, 0x7E)


def test_first_sample_and_each_change_are_reported() -> None:
    """The first colour shows, and then each new one with the time it appeared."""
    samples = [(0.0, PURPLE), (0.1, PURPLE), (0.2, SHIFTED), (0.3, SHIFTED)]
    assert list(colour_changes(samples, 2)) == [(0.0, PURPLE), (0.2, SHIFTED)]


def test_tolerance_hides_coding_wobble() -> None:
    """A channel moving within the tolerance isn't a change; one past it is."""
    near = (PURPLE[0] + 2, PURPLE[1], PURPLE[2])
    far = (PURPLE[0] + 3, PURPLE[1], PURPLE[2])
    assert list(colour_changes([(0.0, PURPLE), (0.1, near)], 2)) == [(0.0, PURPLE)]
    assert list(colour_changes([(0.0, PURPLE), (0.1, far)], 2))[-1] == (0.1, far)


def test_slow_fade_still_shows() -> None:
    """Steps each within the tolerance add up, since the last reported colour is the base."""
    steps = [(float(n), (n * 2, 0, 0)) for n in range(4)]
    assert [time for time, _ in colour_changes(steps, 2)] == [0.0, 2.0]


def test_hex_colour_reads_as_the_docs_do() -> None:
    """Colours print as in the issues: lower-case `#rrggbb`."""
    assert hex_colour(PURPLE) == "#680579"


def test_pair_splits_a_position() -> None:
    """An option such as `540,1200` becomes its integers."""
    assert pair("540,1200") == (540, 1200)
