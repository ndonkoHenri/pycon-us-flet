"""Developer (``/more/developer``): the options for testing and demos (DEV-01, D-73).

The fake clock, in conference time, with a date picker and a time picker
(``developer_clock.py``); the time zone; the feed URL; and the capability flags,
read-only (``capabilities.py``, D-63). Apply puts the clock and the feed URL into effect
at once and saves them in ``pycon.dev``, so they hold across launches; Reset returns to
real time and the year's feed (D-187). The screen is always available when not embedded,
and in a packaged build once unlocked in About this app; a warning-tone "Developer" chip
at its top marks it (ux.md §5.13). #107 adds the data actions (Refresh now, Clear cached
feed, Reset app, Share log).
"""

from datetime import datetime, timedelta

import flet as ft
from flet.utils import is_embedded

from pycon_us import capabilities, clock
from pycon_us.core.timefmt import utc_offset_label
from pycon_us.prefs import parse_feed_url, use_prefs, with_dev_options
from pycon_us.screens.developer_clock import clock_picker
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import Storage
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader

CAPABILITIES = (
    ("Secure storage", capabilities.SECURE_STORAGE),
    ("Permissions", capabilities.PERMISSIONS),
    ("Reminders", capabilities.REMINDERS),
    ("Badge scanner", capabilities.SCANNER),
)
"""The capability flags the screen shows, fixed at import as they are (D-63)."""

NO_OUTCOME: tuple[str, bool] = ("", True)
"""The outcome line's state before Apply or Reset and after an edit: no words, hidden."""


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
    clock_text, set_clock_text = ft.use_state(
        lambda: clock.fake_clock_text(prefs.fake_now, zone)
    )
    url_text, set_url_text = ft.use_state(lambda: prefs.feed_url or "")
    clock_error, set_clock_error = ft.use_state("")  # "" while the field is fine
    url_error, set_url_error = ft.use_state("")
    # What the last Apply or Reset did and whether it was saved, said under the buttons
    # (in place, D-29: a SnackBar from a pushed View shows on the root under it, #197).
    outcome, set_outcome = ft.use_state(NO_OUTCOME)

    @report_errors
    def edit_clock(e: ft.Event[ft.TextField]) -> None:
        set_clock_text(e.control.value)
        set_clock_error("")
        set_outcome(NO_OUTCOME)

    @report_errors
    def edit_url(e: ft.Event[ft.TextField]) -> None:
        set_url_text(e.control.value)
        set_url_error("")
        set_outcome(NO_OUTCOME)

    @report_errors
    def fill_clock(moment: datetime) -> None:
        set_clock_text(clock.fake_clock_text(moment, zone))
        set_clock_error("")
        set_outcome(NO_OUTCOME)  # a fill is an edit (ux.md §5.13)

    @report_errors
    async def apply() -> None:
        valid = True
        fake_now = feed_url = None
        try:
            fake_now = clock.parse_fake_clock(clock_text, zone)
        except ValueError as error:
            set_clock_error(str(error))
            valid = False
        try:
            feed_url = parse_feed_url(url_text)
        except ValueError as error:
            set_url_error(str(error))
            valid = False
        if not valid:
            set_outcome(NO_OUTCOME)
            return
        # Before the save: the re-render it causes reads the new clock (D-187). An
        # unchanged start keeps the clock running instead of setting it back.
        if fake_now != prefs.fake_now:
            clock.start_fake_clock(fake_now)
        conference.set_feed_url(feed_url)
        await leave_test_feed(svc.storage, prefs.feed_url, feed_url)
        dev = with_dev_options(prefs.dev, fake_now=fake_now, feed_url=feed_url)
        saved = await prefs.save(svc.storage, dev=dev)
        set_outcome((applied(fake_now, feed_url, info.time_zone_name), saved))

    @report_errors
    async def reset() -> None:
        set_clock_text("")
        set_url_text("")
        set_clock_error("")
        set_url_error("")
        clock.start_fake_clock(None)
        conference.set_feed_url(None)
        await leave_test_feed(svc.storage, prefs.feed_url, None)
        dev = with_dev_options(prefs.dev, fake_now=None, feed_url=None)
        saved = await prefs.save(svc.storage, dev=dev)
        set_outcome(("Back to real time and the year's feed.", saved))

    chip = developer_chip(tokens.warning)
    if not prefs.developer:  # a packaged build opened here before the unlock (D-73)
        return AppScaffold(title="Developer options", body=locked())
    now = clock.now()
    return AppScaffold(
        title="Developer options",
        body=ft.ListView(
            [
                # The mark opens the page rather than sitting in the app bar: there,
                # at 200 % text it pushed the title out ("Develope…").
                padded(
                    ft.Column(
                        [
                            chip,
                            ft.Text(
                                "For testing and demos. Apply keeps these on this "
                                "device until you reset them.",
                                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=8,
                    )
                ),
                SectionHeader("Clock"),
                option_field(
                    "developer.fake_clock",
                    clock_text,
                    label="Fake clock",
                    hint=f"{info.first_day.isoformat()} 09:00",
                    helper=f"YYYY-MM-DD HH:MM, in {info.time_zone_name}. "
                    "Empty for real time.",
                    error=clock_error,
                    keyboard=ft.KeyboardType.DATETIME,
                    on_change=edit_clock,
                    suffix=clock_picker(
                        page, text=clock_text, info=info, on_pick=fill_clock
                    ),
                ),
                ft.ListTile(
                    title="Time zone",
                    subtitle=zone_line(info.time_zone_name, info.time_zone, now),
                ),
                SectionHeader("Schedule feed"),
                option_field(
                    "developer.feed_url",
                    url_text,
                    label="Feed URL",
                    hint=info.feed_url,
                    helper="Empty for the year's feed. Used from the next refresh.",
                    error=url_error,
                    keyboard=ft.KeyboardType.URL,
                    on_change=edit_url,
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
                ft.Semantics(
                    identifier="developer.outcome",
                    live_region=True,
                    visible=bool(outcome[0]),
                    content=outcome_line(*outcome, tokens=tokens),
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


async def leave_test_feed(storage: Storage, was: str | None, now: str | None) -> None:
    """Delete the feed cache when Apply or Reset leaves a Developer feed URL (D-187).

    The cache may hold that feed's data, which an offline start would publish as the
    schedule; without the cache, that start uses the bundled snapshot.

    Args:
        storage: Where the feed cache lives.
        was: The feed URL in effect until now (``Prefs.feed_url``), or None.
        now: The one that replaces it, or None for the year's feed.
    """
    if was is not None and now is None:
        await storage.delete_feed("the Developer feed URL is off")


def option_field(
    identifier: str,
    value: str,
    *,
    label: str,
    hint: str,
    helper: str,
    error: str,
    keyboard: ft.KeyboardType,
    on_change: ft.ControlEventHandler[ft.TextField],
    suffix: ft.Control | None = None,
) -> ft.Control:
    """Return one option's text field, found by flows through ``identifier``.

    Controlled (D-157): ``value`` comes from the state ``on_change`` sets. The value,
    the helper and the error (``""`` when the text parses) wrap to three lines at large
    text, and the text is taken as typed, with no autocorrect or suggestions (a date, a
    URL). ``max_lines`` without ``multiline``, which would swap ``keyboard`` for the
    multiline keyboard, whose Return types a line break.
    """
    return padded(
        ft.Semantics(
            identifier=identifier,
            content=ft.TextField(
                value=value,
                max_lines=3,
                label=label,
                hint_text=hint,
                hint_max_lines=1,  # else a long hint (the feed URL) heightens the field
                helper=helper,
                helper_max_lines=3,
                error=error or None,
                error_max_lines=3,
                keyboard_type=keyboard,
                autocorrect=False,
                enable_suggestions=False,
                on_change=on_change,
                suffix_icon=suffix,
            ),
        )
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


def outcome_line(done: str, saved: bool, *, tokens: Tokens) -> ft.Control:
    """Return the line under the buttons: an icon and what was done, or that it won't last.

    Args:
        done: What was done, e.g. "Back to real time and the year's feed."
        saved: Whether ``Prefs.save`` saved it; if not, it ends with the app (D-120).
        tokens: The scheme's tokens: ``success``, or ``warning`` when not saved.
    """
    if not saved:
        done += " Couldn't save your change: it ends when you close the app."
    return padded(
        ft.Row(
            [
                # Decorative: the words carry the meaning (ux.md §9).
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_OUTLINE if saved else ft.Icons.WARNING_AMBER,
                    color=tokens.success if saved else tokens.warning,
                    size=20,
                ),
                ft.Text(
                    done,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE,
                    expand=True,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )


def applied(fake_now: datetime | None, feed_url: str | None, zone_name: str) -> str:
    """Return what Apply put into effect, in words.

    Args:
        fake_now: The fake clock's start, or None for real time.
        feed_url: The feed URL, or None for the year's.
        zone_name: The conference zone's name, e.g. "Pacific Time".
    """
    clock_part = "real time" if fake_now is None else f"a fake clock in {zone_name}"
    feed_part = "the year's feed" if feed_url is None else "your feed URL"
    return f"Applied: {clock_part} and {feed_part}."


def developer_chip(color: str) -> ft.Control:
    """Return the warning-tone "Developer" mark at the top of the page (ux.md §5.13).

    A chip's look without a ``Chip``: a Chip with no handler is drawn disabled (faded
    label) at the pin, and a mark is not a control (ux.md §3.9, as ``TrackBadge``).
    Text only, as a badge: a fixed-size icon looked lost beside the label at 200 % text.

    Args:
        color: ``Tokens.warning``: the label and the outline.
    """
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        border=ft.Border.all(1, color),
        border_radius=8,
        content=ft.Text(
            "Developer", theme_style=ft.TextThemeStyle.LABEL_LARGE, color=color
        ),
    )


def zone_line(zone_name: str, zone_key: str, now: datetime) -> str:
    """Return the time-zone row: the conference's zone and the device's offset (D-35).

    Args:
        zone_name: The conference zone's display name, e.g. "Pacific Time".
        zone_key: Its IANA key, e.g. "America/Los_Angeles".
        now: ``clock.now()``; the device's offset is the one at that instant.
    """
    offset = now.astimezone().utcoffset() or timedelta(0)
    return f"{zone_name} ({zone_key}). This device: {utc_offset_label(offset)}."
