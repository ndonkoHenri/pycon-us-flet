"""Tests for the Developer screen: its controls, fields and flags (#88; D-73).

The fixtures and lookups are `tests/developer_screen.py`'s; Apply, Reset and the
pickers are `test_developer_apply.py`'s. The parsing helpers are pure; the pickers on
their own are `test_developer_clock.py`'s. How the screen looks, and the pickers on a
device, are checked on devices (the PR).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import flet as ft

from pycon_us import capabilities
from pycon_us.prefs import Prefs
from pycon_us.screens import developer
from pycon_us.screens.developer import zone_line
from pycon_us.theme import LIGHT_TOKENS
from tests import developer_screen
from tests.developer_screen import (
    FEED,
    by_identifier,
    clock_picker_button,
    field,
    merged_identifiers,
)

real_time, page, svc, prefs, conference, render = (
    developer_screen.real_time,
    developer_screen.page,
    developer_screen.svc,
    developer_screen.prefs,
    developer_screen.conference,
    developer_screen.render,
)

# ------------------------------------------------------------------ the screen


def test_the_controls_carry_the_identifiers_ui_flows_use(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Developer options carries exactly the identifiers the UI flows use."""
    scaffold = render()
    assert set(by_identifier(scaffold)) == {
        "developer.fake_clock",
        "developer.feed_url",
        "developer.reset",
        "developer.apply",
        "developer.outcome",
    }
    assert scaffold["title"] == "Developer options"


def test_the_buttons_and_the_url_field_are_one_node_with_their_identifier(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Reset, Apply, the URL field and the clock picker each merge their identifier.

    A bare Semantics(identifier) around a control dumped as an empty, focusable View
    beside the button on Android (#236); merged, the control's own node carries it
    (D-190).
    """
    assert merged_identifiers(render()) == {
        "developer.reset",
        "developer.apply",
        "developer.feed_url",
        "developer.clock_picker",
    }
    nodes = by_identifier(render())
    assert isinstance(nodes["developer.reset"], ft.OutlinedButton)
    assert isinstance(nodes["developer.apply"], ft.FilledButton)
    assert isinstance(nodes["developer.feed_url"], ft.TextField)


def test_the_clock_field_keeps_its_picker_a_button_of_its_own(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The clock field's identifier stays unmerged, so its picker is its own node.

    A merge takes in every descendant: around the clock field it would make the picker
    part of the field's node (D-189), so that identifier stays bare (U34).
    """
    scaffold = render()
    assert "developer.fake_clock" not in merged_identifiers(scaffold)
    assert clock_picker_button(field(scaffold, "developer.fake_clock"))


def test_a_warning_tone_chip_marks_the_screen(
    render: Callable[[], dict[str, Any]],
) -> None:
    """A text-only Developer chip in the warning colour, with no tap, tops the list."""
    scaffold = render()
    assert "actions" not in scaffold  # at 200 % text it pushed the title out
    top = cast(ft.ListView, scaffold["body"]).controls[0]
    assert isinstance(top, ft.Container) and isinstance(top.content, ft.Column)
    chip = top.content.controls[0]
    assert isinstance(chip, ft.Container)
    assert chip.border == ft.Border.all(1, LIGHT_TOKENS.warning)
    assert chip.on_click is None  # a mark, not a control
    label = chip.content  # text only: a fixed-size icon looked lost at 200 % text
    assert isinstance(label, ft.Text) and label.value == "Developer"
    assert label.color == LIGHT_TOKENS.warning


def test_the_fields_show_what_is_in_effect(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """The fields show the stored fake clock in Pacific Time and the stored feed URL."""
    prefs.dev = {
        "unlocked": True,
        "fake_now": "2026-05-15T16:00:00+00:00",
        "feed_url": FEED,
    }
    scaffold = render()
    assert field(scaffold, "developer.fake_clock").value == "2026-05-15 09:00"  # PDT
    assert field(scaffold, "developer.feed_url").value == FEED


def helper(text_field: ft.TextField) -> ft.Text:
    """A field's helper, a `Text` in Material's helper style."""
    text = text_field.helper
    assert isinstance(text, ft.Text)
    assert text.theme_style == ft.TextThemeStyle.BODY_SMALL
    assert text.color == ft.Colors.ON_SURFACE_VARIANT
    return text


def test_the_fields_say_the_clock_s_format_and_wrap_at_large_text(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The clock's helper gives its format, and both fields wrap up to three lines."""
    scaffold = render()
    clock_field = field(scaffold, "developer.fake_clock")
    assert helper(clock_field).value == (
        "YYYY-MM-DD HH:MM, in Pacific Time. Empty for real time."
    )
    for text_field in (clock_field, field(scaffold, "developer.feed_url")):
        assert text_field.max_lines == 3  # wraps instead of hiding the end
        assert text_field.hint_max_lines == 1  # an empty field keeps one line
        # Not multiline: it would swap in the multiline keyboard, whose Return types
        # a line break, for the date-time and URL keyboards.
        assert text_field.multiline is False
    assert clock_field.keyboard_type == ft.KeyboardType.DATETIME


def test_the_helpers_are_shown_in_full_at_the_largest_text(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Both fields' helpers are Texts with no line limit and no ellipsis.

    A string helper is cut at helper_max_lines, and null is one line: at three, the
    largest text cut the clock's at "Empty for r…", the way back to real time (#280).
    """
    scaffold = render()
    for identifier in ("developer.fake_clock", "developer.feed_url"):
        text_field = field(scaffold, identifier)
        assert text_field.helper_max_lines is None  # the Text helper ignores it
        text = helper(text_field)
        assert text.max_lines is None
        assert text.overflow in (None, ft.TextOverflow.CLIP)  # no ellipsis


def test_reset_and_apply_keep_their_padding_at_large_text(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Reset and Apply pin a 24 dp side padding, and Apply lies flat.

    Flutter shrinks a button's side padding as the text grows: at the largest text the
    labels touched the rounded ends (#280), as the Schedule sheet's Show did.
    """
    nodes = by_identifier(render())
    for identifier in ("developer.reset", "developer.apply"):
        button = nodes[identifier]
        assert isinstance(button, ft.OutlinedButton | ft.FilledButton)
        assert button.style is not None
        assert button.style.padding == ft.Padding.symmetric(horizontal=24, vertical=8)
    apply = nodes["developer.apply"]
    # With a style, Flet lifts every state to the button's elevation: M3's lies flat.
    assert isinstance(apply, ft.FilledButton) and apply.elevation == 0


def test_the_url_field_keeps_apply_in_sight_above_the_keyboard(
    render: Callable[[], dict[str, Any]],
) -> None:
    """The URL field's scroll padding keeps Apply in sight; the clock's stays 20 dp.

    Focused, the field scrolls its helper and the Reset and Apply row under it into
    sight, so a URL can be typed and applied without closing the keyboard (#108).
    """
    scaffold = render()
    url_padding = field(scaffold, "developer.feed_url").scroll_padding
    assert url_padding == ft.Padding.only(
        left=20, top=20, right=20, bottom=developer.APPLY_IN_SIGHT
    )
    # The clock field keeps Flutter's 20 dp: Apply is far below it.
    clock_padding = field(scaffold, "developer.fake_clock").scroll_padding
    assert clock_padding == ft.Padding.only(left=20, top=20, right=20, bottom=20)


def test_before_the_unlock_a_packaged_build_shows_how_to_unlock(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """Before the unlock, a packaged build's screen has no option to change."""
    prefs.dev = {}
    scaffold = render()
    assert by_identifier(scaffold) == {}  # no options to change


def test_the_capability_flags_are_shown_read_only(
    render: Callable[[], dict[str, Any]],
) -> None:
    """Each capability flag is a tile saying whether this build has it, with no tap."""
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    rows = [
        (row.title, row.subtitle)
        for row in body.controls
        if isinstance(row, ft.ListTile) and row.title != "Time zone"
    ]
    # The constants, as fixed at import (D-63); in pytest, no packaged build bundles them.
    assert rows == [
        (name, "In this build" if on else "Not in this build")
        for name, on in [
            ("Secure storage", capabilities.SECURE_STORAGE),
            ("Permissions", capabilities.PERMISSIONS),
            ("Reminders", capabilities.REMINDERS),
            ("Badge scanner", capabilities.SCANNER),
        ]
    ]
    assert all(
        row.on_click is None for row in body.controls if isinstance(row, ft.ListTile)
    )


# ------------------------------------------------------------------ the helpers


def test_the_time_zone_row_names_the_conference_zone_and_the_device_offset() -> None:
    """The time zone line names Pacific Time, its IANA key and the device's offset."""
    line = zone_line("Pacific Time", "America/Los_Angeles", datetime.now(UTC))
    assert line.startswith("Pacific Time (America/Los_Angeles). This device: UTC")
