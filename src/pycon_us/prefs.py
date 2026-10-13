"""The ``Prefs`` store: the user's settings and the device facts they depend on (D-69).

It holds the six app-wide keys of the storage table (decisions §M), checks the two
settings with fixed values (Appearance, High contrast) on load and on save, and keeps
what the user chose in memory when a write fails (D-120). ``App`` reads it before the
first screen (the boot gate), so neither the theme nor the filters flash.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

import flet as ft

from pycon_us.services.storage import (
    DEV,
    EXCLUDED_TRACKS,
    HIGH_CONTRAST,
    ONBOARDED,
    REMINDERS,
    THEME,
    Pref,
    Storage,
)

logger = logging.getLogger(__name__)

type Appearance = Literal["system", "light", "dark"]
"""The Appearance setting (THEME-01): follow the OS, or always light or dark."""

type HighContrast = Literal["system", "on", "off"]
"""The High contrast setting (D-23): follow the OS flag, or always on or off."""

APPEARANCES: tuple[Appearance, ...] = get_args(Appearance.__value__)
"""Appearance's values; the first is the default, as in the storage table."""

HIGH_CONTRAST_SETTINGS: tuple[HighContrast, ...] = get_args(HighContrast.__value__)
"""High contrast's values; the first is the default, as in the storage table."""

_PERSISTED: dict[str, Pref[Any]] = {
    "theme": THEME,
    "high_contrast": HIGH_CONTRAST,
    "onboarded": ONBOARDED,
    "excluded_tracks": EXCLUDED_TRACKS,
    "reminders": REMINDERS,
    "dev": DEV,
}
"""The persisted fields of ``Prefs`` and their keys in the storage table (decisions §M)."""


@ft.observable
@dataclass(eq=False)
class Prefs:
    """The user's settings, persisted, and the device facts they resolve against (D-69).

    ``App`` shows the boot view until ``loaded`` (D-69), so no screen ever renders
    with a default theme or filter before the stored one is read. Replace a value with
    ``save()``; never mutate a field in place, since only ``save()`` persists.

    Attributes:
        theme: The Appearance setting (``pycon.theme``).
        high_contrast: The High contrast setting (``pycon.high_contrast``); until P2
            the standard schemes show whatever it says (``theme.build_theme``).
        onboarded: Whether Welcome was seen (``pycon.onboarded``, P2).
        excluded_tracks: Track keys hidden from the Schedule (``pycon.excluded_tracks``;
            by default Open Space, D-20).
        reminders: Reminder settings (``pycon.reminders``, P2).
        dev: Developer options (``pycon.dev``, D-73).
        os_dark: The OS is in dark mode; not persisted, kept current by ``App``.
        os_high_contrast: The OS asks for high contrast (iOS, Android 34+); not
            persisted, read at start and on resume (F13).
        reduce_motion: The OS asks for less motion (D-34): iOS Reduce Motion or
            Android's Remove animations. Not persisted, read at start and on resume;
            ask through ``motion_ms()``.
        screen_reader: A screen reader is on (TalkBack, VoiceOver; Flutter's
            ``accessible_navigation``). Not persisted, read at start and on resume;
            an Undo SnackBar then stays until it is used or replaced (D-184).
        loaded: The stored values have been read; it opens the boot gate.
    """

    theme: Appearance = "system"
    high_contrast: HighContrast = "system"
    onboarded: bool = False
    excluded_tracks: tuple[str, ...] = tuple(EXCLUDED_TRACKS.default)
    reminders: dict[str, Any] = field(default_factory=dict)
    dev: dict[str, Any] = field(default_factory=dict)
    os_dark: bool = False
    os_high_contrast: bool = False
    reduce_motion: bool = False
    screen_reader: bool = False
    loaded: bool = False

    @property
    def dark(self) -> bool:
        """Whether the dark scheme is on screen: Appearance, or the OS under System."""
        return self.theme == "dark" or (self.theme == "system" and self.os_dark)

    @property
    def high_contrast_on(self) -> bool:
        """Whether high contrast applies: the setting, or the OS flag under System."""
        if self.high_contrast == "system":
            return self.os_high_contrast
        return self.high_contrast == "on"

    def motion_ms(self, ms: int) -> int:
        """Return how long an animation of ``ms`` milliseconds runs: 0 under reduced motion.

        The one way the app asks about motion (D-34, D-173): pass the result as a
        ``scroll_to(duration=...)``, an ``animate_*`` or any other duration, so the
        motion becomes a jump when the OS asks for less of it.

        Args:
            ms: The M3 duration the animation has otherwise (ux.md §3.8).

        Returns:
            ``ms``, or 0 when the OS asks for reduced motion (``reduce_motion``).
        """
        return 0 if self.reduce_motion else ms

    async def load(self, storage: Storage) -> None:
        """Read every persisted setting; an unreadable or unknown value reads as its default.

        Storage logs what it cannot read (D-120); an Appearance or High contrast value
        that is not one of the settings' values is logged here. ``loaded`` is left to the
        caller, which opens the boot gate once the feed is published too.

        Args:
            storage: Where the settings are kept.
        """
        theme: Appearance = _choice(THEME, await storage.get(THEME), APPEARANCES)
        high_contrast: HighContrast = _choice(
            HIGH_CONTRAST, await storage.get(HIGH_CONTRAST), HIGH_CONTRAST_SETTINGS
        )
        onboarded = await storage.get(ONBOARDED)
        excluded_tracks = tuple(await storage.get(EXCLUDED_TRACKS))
        reminders = await storage.get(REMINDERS)
        dev = await storage.get(DEV)
        # Assigned together, after the reads: one re-render, never a half-read state.
        self.theme = theme
        self.high_contrast = high_contrast
        self.onboarded = onboarded
        self.excluded_tracks = excluded_tracks
        self.reminders = reminders
        self.dev = dev

    async def save(
        self,
        storage: Storage,
        *,
        theme: Appearance | None = None,
        high_contrast: HighContrast | None = None,
        onboarded: bool | None = None,
        excluded_tracks: tuple[str, ...] | None = None,
        reminders: dict[str, Any] | None = None,
        dev: dict[str, Any] | None = None,
    ) -> bool:
        """Persist the given settings, then show them; arguments left None are unchanged.

        The new values are assigned even when a write fails, so the session shows what
        the user chose (D-120). The caller then says it was not saved, e.g. with a
        SnackBar "Couldn't save your change", since it will be lost on relaunch.

        Args:
            storage: Where the settings are kept.
            theme: The new Appearance.
            high_contrast: The new High contrast setting.
            onboarded: Whether Welcome was seen.
            excluded_tracks: The track keys to hide; ``()`` hides none.
            reminders: The new reminder settings.
            dev: The new developer options.

        Returns:
            Whether every write succeeded; failures are logged by ``Storage``.

        Raises:
            ValueError: ``theme`` or ``high_contrast`` is not one of its setting's values.
        """
        if theme is not None and theme not in APPEARANCES:
            raise ValueError(f"theme must be one of {APPEARANCES}, not {theme!r}")
        if high_contrast is not None and high_contrast not in HIGH_CONTRAST_SETTINGS:
            raise ValueError(
                f"high_contrast must be one of {HIGH_CONTRAST_SETTINGS}, "
                f"not {high_contrast!r}"
            )
        changes = {
            "theme": theme,
            "high_contrast": high_contrast,
            "onboarded": onboarded,
            "excluded_tracks": excluded_tracks,
            "reminders": reminders,
            "dev": dev,
        }
        changes = {name: value for name, value in changes.items() if value is not None}
        saved = True
        for name, value in changes.items():
            # SharedPreferences takes list[str], not tuples (F12).
            stored = list(value) if isinstance(value, tuple) else value
            saved = await storage.set(_PERSISTED[name], stored) and saved
        for name, value in changes.items():
            setattr(self, name, value)
        return saved


def _choice[T: str](pref: Pref[str], value: str, choices: tuple[T, ...]) -> T:
    """Return ``value`` when it is one of ``choices``, else the first, the default (logged)."""
    for choice in choices:
        if value == choice:
            return choice
    logger.warning("Preference %s has an unknown value; using its default", pref.key)
    return choices[0]


PrefsCtx: ft.ContextProvider[Prefs | None] = ft.create_context(None)
"""Provides the session's ``Prefs``; ``App`` writes the provider out (D-69)."""


def use_prefs() -> Prefs:
    """Return the ``Prefs`` store and re-render the caller when it changes (F3).

    Raises:
        RuntimeError: No ``PrefsCtx`` provider is above the calling component.
    """
    prefs = ft.use_context(PrefsCtx)
    if prefs is None:
        raise RuntimeError("use_prefs() needs a PrefsCtx provider above it")
    return prefs
