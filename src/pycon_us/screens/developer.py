"""Developer (``/more/developer``): the options for testing and demos (DEV-01, D-73).

The fake clock, in conference time, with a date picker and a time picker
(``developer_clock.py``); the time zone; the feed URL; and the capability flags,
read-only (``capabilities.py``, D-63). Apply puts the clock and the feed URL into effect
at once and saves them in ``pycon.dev``, so they hold across launches; Reset returns to
real time and the year's feed (D-187). The screen is always available when not embedded,
and in a packaged build once unlocked in About this app; a warning-tone "Developer" chip
at its top marks it (ux.md §5.13). Its Data section (Refresh now, Clear cached feed,
Share log, Reset app) is ``developer_data.py``'s (D-198).
"""

from datetime import datetime, timedelta

import flet as ft
from flet.utils import is_embedded

from pycon_us import capabilities, clock
from pycon_us.core.timefmt import utc_offset_label
from pycon_us.prefs import parse_feed_url, use_prefs, with_dev_options
from pycon_us.screens.developer_clock import clock_picker
from pycon_us.screens.developer_data import DataActions
from pycon_us.screens.developer_ui import LABEL_PADDING, option_field
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import NO_OUTCOME, outcome_line, padded
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named

APPLY_IN_SIGHT = 304
"""How far below its text the feed URL field keeps in sight when it takes the focus,
in dp: its helper line, the Reset and Apply row under it and the outcome line that
says what Apply did. The keyboard covers half the screen, and without this the list
stopped at the field, Apply hidden under the keyboard (#108); Flutter's default keeps
20 dp. Flet does not tell the app its text scale, so it is sized for large text: at
200 % on Android the outcome's two lines stay in sight too, and at iOS's largest size
the Apply row does, where 168 dp, enough at 100 %, left the outcome (Android) or Apply
(iOS) under the keyboard. At 100 % the list only scrolls a little further."""


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
    # What the last Apply or Reset did and whether it was saved, said under the buttons:
    # a result the user waits for appears in place (D-29, D-210).
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
        # Leaving a feed URL for the year's deletes the cache it may have filled (D-244).
        await conference.set_feed_url(feed_url, svc.storage)
        dev = with_dev_options(prefs.dev, fake_now=fake_now, feed_url=feed_url)
        saved = await prefs.save(svc.storage, dev=dev)
        set_outcome(said(applied(fake_now, feed_url, info.time_zone_name), saved))

    @report_errors
    async def reset() -> None:
        set_clock_text("")
        set_url_text("")
        set_clock_error("")
        set_url_error("")
        clock.start_fake_clock(None)
        await conference.set_feed_url(None, svc.storage)
        dev = with_dev_options(prefs.dev, fake_now=None, feed_url=None)
        saved = await prefs.save(svc.storage, dev=dev)
        set_outcome(said("Back to real time and the year's feed.", saved))

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
                    # Merged: unwrapped, its tooltip and its button were two
                    # nodes, the button unnamed (D-214).
                    suffix=named(
                        "developer.clock_picker",
                        clock_picker(
                            page, text=clock_text, info=info, on_pick=fill_clock
                        ),
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
                    # Apply sits right below: typing a URL, then Apply, needs no
                    # closing of the keyboard first.
                    reveal_below=APPLY_IN_SIGHT,
                ),
                padded(
                    ft.Row(
                        [
                            # Merged: a bare identifier was an empty stop (D-190).
                            # Their own padding, as the Schedule sheet's Show: Flutter
                            # shrinks it as the text grows, and at the largest text
                            # the labels touched the rounded ends (#280).
                            named(
                                "developer.reset",
                                ft.OutlinedButton(
                                    "Reset",
                                    on_click=reset,
                                    style=ft.ButtonStyle(padding=LABEL_PADDING),
                                ),
                            ),
                            named(
                                "developer.apply",
                                ft.FilledButton(
                                    "Apply",
                                    on_click=apply,
                                    style=ft.ButtonStyle(padding=LABEL_PADDING),
                                    # M3's filled button lies flat; with a style, Flet
                                    # lifts every state to this (1 by default).
                                    elevation=0,
                                ),
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
                SectionHeader("Data"),
                DataActions(),
                SectionHeader("Capabilities"),
                padded(
                    ft.Text(
                        capabilities_note(),
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                ),
                *(capability_row(name, on) for name, on in capabilities.ALL),
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


def said(done: str, saved: bool) -> tuple[str, bool]:
    """Return the outcome line's state after Apply or Reset: what was done, and whether it lasts.

    Args:
        done: What was done, e.g. "Back to real time and the year's feed."
        saved: Whether ``Prefs.save`` saved it; if not, it ends with the app (D-120),
            which the line says, beside a warning icon.
    """
    if not saved:
        done += " Couldn't save your change: it ends when you close the app."
    return done, saved


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
