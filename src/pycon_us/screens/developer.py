"""Developer (``/more/developer``): the options for testing and demos (DEV-01, D-73).

The fake clock, in conference time, with a date picker and a time picker; the time zone;
the feed URL; and the capability flags, read-only (``capabilities.py``, D-63). Apply puts
the clock and the feed URL into effect at once and saves them in ``pycon.dev``, so they
hold across launches; Reset returns to real time and the year's feed (D-184). The screen
is always available when not embedded, and in a packaged build once unlocked in About
this app; a warning-tone "Developer" chip marks it (ux.md §5.13). #107 adds the data
actions (Refresh now, Clear cached feed, Reset app, Share log).
"""

from datetime import date, datetime, timedelta, tzinfo
from typing import Any
from urllib.parse import urlsplit

import flet as ft
from flet.utils import is_embedded

from pycon_us import capabilities, clock
from pycon_us.prefs import DEV_FAKE_NOW, DEV_FEED_URL, Prefs, use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import Storage
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader

CLOCK_FORMAT = "%Y-%m-%d %H:%M"
"""How the fake-clock field writes an instant: ISO 8601 with a space, in conference time."""

CAPABILITIES = (
    ("Secure storage", capabilities.SECURE_STORAGE),
    ("Permissions", capabilities.PERMISSIONS),
    ("Reminders", capabilities.REMINDERS),
    ("Badge scanner", capabilities.SCANNER),
)
"""The capability flags the screen shows, fixed at import as they are (D-63)."""


@ft.component
def Developer() -> ft.View:
    """The Developer screen: the fake clock, the feed URL and the build's capabilities."""
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()
    conference = use_conference()
    tokens = use_tokens()
    info = svc.year.conference
    zone = info.zone
    # Controlled fields (D-157), seeded from what is in effect.
    clock_text, set_clock_text = ft.use_state(lambda: clock_field(prefs.fake_now, zone))
    url_text, set_url_text = ft.use_state(lambda: prefs.feed_url or "")
    clock_error, set_clock_error = ft.use_state("")  # "" while the field is fine
    url_error, set_url_error = ft.use_state("")
    picked_day = ft.use_ref(None)  # the date picker's day, until the time is picked

    @report_errors
    def edit_clock(e: ft.Event[ft.TextField]) -> None:
        set_clock_text(e.control.value)
        set_clock_error("")

    @report_errors
    def edit_url(e: ft.Event[ft.TextField]) -> None:
        set_url_text(e.control.value)
        set_url_error("")

    @report_errors
    def pick_time(e: ft.Event[ft.TimePicker]) -> None:
        if picked_day.current is not None and e.control.value is not None:
            moment = datetime.combine(picked_day.current, e.control.value, zone)
            set_clock_text(moment.strftime(CLOCK_FORMAT))
            set_clock_error("")

    @report_errors
    def pick_day(e: ft.Event[ft.DatePicker]) -> None:
        if e.control.value is None:
            return
        picked_day.current = picked_date(e.control.value)
        start = shown_start(clock_text, zone)
        page.show_dialog(
            ft.TimePicker(
                value=start.time(),
                help_text=f"Time in {info.time_zone_name}",
                on_change=pick_time,
            )
        )

    @report_errors
    def pick() -> None:
        start = shown_start(clock_text, zone)
        page.show_dialog(
            ft.DatePicker(
                value=start.date(),
                first_date=date(info.year - 1, 1, 1),
                last_date=date(info.year + 1, 12, 31),
                help_text="Fake clock date",
                on_change=pick_day,
            )
        )

    @report_errors
    async def apply() -> None:
        valid = True
        fake_now = feed_url = None
        try:
            fake_now = parse_fake_clock(clock_text, zone)
        except ValueError as error:
            set_clock_error(str(error))
            valid = False
        try:
            feed_url = parse_feed_url(url_text)
        except ValueError as error:
            set_url_error(str(error))
            valid = False
        if not valid:
            return
        # Before the save: the re-render it causes reads the new clock (D-184). An
        # unchanged start keeps the clock running instead of setting it back.
        if fake_now != prefs.fake_now:
            clock.start_fake_clock(fake_now)
        conference.set_feed_url(feed_url)
        dev = dev_options(prefs.dev, fake_now, feed_url)
        await save(page, prefs, svc.storage, dev, "Developer options applied")

    @report_errors
    async def reset() -> None:
        set_clock_text("")
        set_url_text("")
        set_clock_error("")
        set_url_error("")
        clock.start_fake_clock(None)
        conference.set_feed_url(None)
        dev = dev_options(prefs.dev, None, None)
        await save(
            page, prefs, svc.storage, dev, "Back to real time and the year's feed"
        )

    chip = ft.Container(
        padding=ft.Padding.only(right=16),
        content=ft.Chip(
            label="Developer",
            leading=ft.Icon(ft.Icons.DEVELOPER_MODE_OUTLINED, color=tokens.warning),
            label_text_style=ft.TextStyle(color=tokens.warning),
            border_side=ft.BorderSide(1, tokens.warning),
        ),
    )
    if not prefs.developer:  # a packaged build opened here before the unlock (D-73)
        return AppScaffold(title="Developer options", body=locked())
    now = clock.now()
    return AppScaffold(
        title="Developer options",
        actions=[chip],
        body=ft.ListView(
            [
                padded(
                    ft.Text(
                        "For testing and demos. Apply keeps these on this device "
                        "until you reset them.",
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                ),
                SectionHeader("Clock"),
                padded(
                    ft.Semantics(
                        identifier="developer.fake_clock",
                        content=ft.TextField(
                            value=clock_text,
                            label="Fake clock",
                            hint_text=f"{info.first_day.isoformat()} 09:00",
                            helper=f"In {info.time_zone_name}. Empty for real time.",
                            helper_max_lines=3,
                            error=clock_error or None,
                            error_max_lines=3,
                            keyboard_type=ft.KeyboardType.DATETIME,
                            autocorrect=False,
                            enable_suggestions=False,
                            on_change=edit_clock,
                            suffix_icon=ft.IconButton(
                                ft.Icons.EDIT_CALENDAR_OUTLINED,
                                tooltip="Pick a date and time",
                                on_click=pick,
                            ),
                        ),
                    )
                ),
                ft.ListTile(
                    title="Time zone",
                    subtitle=zone_line(info.time_zone_name, info.time_zone, now),
                ),
                SectionHeader("Schedule feed"),
                padded(
                    ft.Semantics(
                        identifier="developer.feed_url",
                        content=ft.TextField(
                            value=url_text,
                            label="Feed URL",
                            hint_text=info.feed_url,
                            helper="Empty for the year's feed. Used from the next "
                            "refresh.",
                            helper_max_lines=3,
                            error=url_error or None,
                            error_max_lines=3,
                            keyboard_type=ft.KeyboardType.URL,
                            autocorrect=False,
                            enable_suggestions=False,
                            on_change=edit_url,
                        ),
                    )
                ),
                padded(
                    ft.Row(
                        [
                            ft.Semantics(
                                identifier="developer.reset",
                                content=ft.OutlinedButton("Reset", on_click=reset),
                            ),
                            ft.Semantics(
                                identifier="developer.apply",
                                content=ft.FilledButton("Apply", on_click=apply),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                        wrap=True,
                    )
                ),
                SectionHeader("Capabilities"),
                padded(
                    ft.Text(
                        capabilities_note(),
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                ),
                *(capability_row(name, on) for name, on in CAPABILITIES),
            ],
            expand=True,
        ),
    )


def locked() -> ft.Control:
    """Return the body shown before the unlock: how to unlock, and the way there."""
    return ft.ListView(
        [
            padded(
                ft.Text(
                    "Developer options are off. Tap the version in About this app "
                    "7 times to turn them on.",
                    theme_style=ft.TextThemeStyle.BODY_LARGE,
                )
            ),
            LinkTile("About this app", "/more/app", icon=ft.Icons.INFO_OUTLINE),
        ],
        expand=True,
    )


def padded(control: ft.Control) -> ft.Container:
    """Return ``control`` with the list's 16 dp sides and 8 dp above and below (ux.md §3.6)."""
    return ft.Container(
        control, padding=ft.Padding.symmetric(horizontal=16, vertical=8)
    )


def capability_row(name: str, available: bool) -> ft.Control:
    """Return one capability flag: its name and, in words, whether this build has it.

    Args:
        name: The capability, e.g. "Reminders".
        available: Its constant in ``capabilities.py``.
    """
    return ft.ListTile(
        leading=ft.Icon(
            ft.Icons.CHECK_CIRCLE_OUTLINE
            if available
            else ft.Icons.REMOVE_CIRCLE_OUTLINE
        ),
        title=name,
        subtitle="In this build" if available else "Not in this build",
    )


def capabilities_note() -> str:
    """Return why the flags are what they are: the build the app runs in (D-63)."""
    if is_embedded():
        return "Read-only: the extensions this packaged build bundles."
    return "Not a packaged build: every capability uses its interim."


async def save(
    page: ft.Page, prefs: Prefs, storage: Storage, dev: dict[str, Any], done: str
) -> None:
    """Save the Developer options and say so; they are in effect even when unsaved.

    Args:
        page: The session's page, for the SnackBar.
        prefs: The ``Prefs`` store.
        storage: Where the settings are kept.
        dev: The new ``Prefs.dev``.
        done: What the SnackBar says once they are saved.
    """
    saved = await prefs.save(storage, dev=dev)
    text = done if saved else "Couldn't save your change"  # lost on relaunch (D-120)
    page.show_dialog(ft.SnackBar(ft.Text(text), behavior=ft.SnackBarBehavior.FLOATING))


def clock_field(moment: datetime | None, zone: tzinfo) -> str:
    """Return the fake-clock field's text for ``moment``: empty for real time.

    Args:
        moment: The fake clock's start, or None.
        zone: The conference's zone, which the field writes in.
    """
    return "" if moment is None else moment.astimezone(zone).strftime(CLOCK_FORMAT)


def parse_fake_clock(text: str, zone: tzinfo) -> datetime | None:
    """Return the instant the fake-clock field names, or None when it is empty.

    Args:
        text: ISO 8601, e.g. ``2026-05-15 09:00`` or ``2026-05-15T09:00:00-07:00``;
            without an offset it is conference time.
        zone: The conference's zone.

    Raises:
        ValueError: The text is not a date and time; its message is the field's error.
    """
    text = text.strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("Write it as YYYY-MM-DD HH:MM") from None
    return moment.replace(tzinfo=zone) if moment.utcoffset() is None else moment


def parse_feed_url(text: str) -> str | None:
    """Return the feed URL the field names, or None when it is empty (the year's feed).

    Args:
        text: An ``http://`` or ``https://`` URL; plain HTTP for a test server on the
            laptop (testing-and-quality.md §5.2).

    Raises:
        ValueError: The text is not such a URL; its message is the field's error.
    """
    text = text.strip()
    if not text:
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Use an http:// or https:// address")
    return text


def dev_options(
    dev: dict[str, Any], fake_now: datetime | None, feed_url: str | None
) -> dict[str, Any]:
    """Return ``Prefs.dev`` with the fake clock and the feed URL set; None removes one.

    Other keys (the unlock) are kept.

    Args:
        dev: The current ``Prefs.dev``.
        fake_now: The fake clock's start, or None for real time.
        feed_url: The feed URL, or None for the year's.
    """
    options = {k: v for k, v in dev.items() if k not in (DEV_FAKE_NOW, DEV_FEED_URL)}
    if fake_now is not None:
        options[DEV_FAKE_NOW] = fake_now.isoformat()
    if feed_url is not None:
        options[DEV_FEED_URL] = feed_url
    return options


def picked_date(value: datetime | date) -> date:
    """Return the day a ``DatePicker`` reports: it sends the device's local midnight in UTC.

    Args:
        value: ``DatePicker.value`` after a pick.
    """
    if isinstance(value, datetime):
        return (
            value.astimezone().date() if value.utcoffset() is not None else value.date()
        )
    return value


def shown_start(text: str, zone: tzinfo) -> datetime:
    """Return where the pickers open: the field's instant, else now, in conference time.

    Args:
        text: The fake-clock field's text.
        zone: The conference's zone.
    """
    try:
        moment = parse_fake_clock(text, zone)
    except ValueError:
        moment = None
    return (moment or clock.now()).astimezone(zone).replace(tzinfo=None)


def zone_line(zone_name: str, zone_key: str, now: datetime) -> str:
    """Return the time-zone row: the conference's zone and the device's offset (D-35).

    Args:
        zone_name: The conference zone's display name, e.g. "Pacific Time".
        zone_key: Its IANA key, e.g. "America/Los_Angeles".
        now: ``clock.now()``; the device's offset is the one at that instant.
    """
    offset = now.astimezone().utcoffset() or timedelta(0)
    return f"{zone_name} ({zone_key}). This device: {utc_offset(offset)}."


def utc_offset(offset: timedelta) -> str:
    """Return a UTC offset as people write it: ``UTC−07:00``, ``UTC+05:30``, ``UTC``.

    Args:
        offset: The offset from UTC.
    """
    if not offset:
        return "UTC"
    sign = "+" if offset > timedelta(0) else "−"  # a minus sign, not a hyphen
    minutes = abs(int(offset.total_seconds())) // 60
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"
