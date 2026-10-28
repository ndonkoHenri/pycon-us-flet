"""The plain diagnostics text a bug report carries (INFO-04, D-72, D-271).

Ionic shared an encrypted dump of every stored key, the API secret included. We share a
few plain lines instead, one fact per line, which a tester can read before sending:
versions, the device, the schedule data and its age, the clock and time zones, the
Developer options in effect, and a few settings and counts. About this app and Help &
safety share it (#443).

Two halves: ``gather_facts()`` reads the ``Facts`` from the page, the stores and the
build; ``diagnostics_text()`` writes them, a pure function. The facts hold nothing
personal to begin with: whether a custom feed URL is set, never the URL; how many
sessions are saved, never which. As a net under that, every value is written on one
line, with its email addresses and URLs replaced (D-196's rule for the log).
"""

import logging
import platform
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import flet as ft
from flet.utils import is_embedded

from pycon_us import FLET_VERSION, capabilities, clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.timefmt import ago_label
from pycon_us.favorites import Favorites
from pycon_us.feed_refresh import Source
from pycon_us.prefs import Prefs
from pycon_us.services.build import read_build
from pycon_us.services.errors import EMAIL, REDACTED_EMAIL
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.state import Conference

logger = logging.getLogger(__name__)

_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S*")
"""A URL with a scheme, query included, as a value could quote one."""

_REDACTED_URL = "<url>"
"""What the text writes in a URL's place."""

NOT_EMBEDDED = "not embedded (companion app or desktop)"
"""The run's line outside a packaged build: Python runs on the laptop (F14)."""

MAX_VALUE = 80
"""The longest value the text writes, in characters; a longer one is cut with "…"."""

_FEED_DIGITS = 12
"""How many hex digits of the feed's SHA-256 name it: enough to tell feeds apart."""

_MEDIUM_FROM = 600
"""Material 3's medium window size class starts here, in dp, as D-09's rail does; under it
is compact."""

_EXPANDED_FROM = 840
"""Material 3's expanded class starts here (D-09's list width)."""


@dataclass(frozen=True)
class Facts:
    """What the diagnostics text says, read once by ``gather_facts()``.

    Attributes:
        app_version: The app's version: ``pycon_us.__version__`` (D-83), or a
            packaged build's own (D-386).
        build_number: A packaged build's number, or None (D-386).
        python: The Python version, e.g. ``3.14.0``.
        flet: The Flet version, ``FLET_VERSION`` while the app builds from source.
        platform: The page's platform, e.g. ``android``.
        device: The device's make and model, and whether it is an emulator or a
            simulator; None when the platform did not say.
        os: The OS and its version, e.g. ``Android 15 (API 35)``; None when the
            platform did not say.
        embedded: A packaged build, not the companion app or a desktop host (F14).
        year: The conference year (``config.YEAR``).
        source: Where the published schedule came from.
        feed_digest: The published feed's SHA-256 (``Conference.digest``), or None.
        fetched_at: When the published schedule was fetched (aware), or None.
        zone: The conference's IANA time zone, e.g. ``America/Los_Angeles``.
        device_offset: The device's UTC offset now (the host's in the companion app).
        fake_clock_from: The fake clock's start (aware), or None for real time.
        now: The app's time, ``clock.now()``: the fake clock's when it is on.
        written_at: The real time the facts were read (aware).
        custom_feed_url: A Developer feed URL is in effect; the URL itself never is
            a fact.
        reduced_motion: The OS asks for less motion (D-34).
        width: The page's width in dp, or None before Flutter reported it.
        capabilities: The names of the capabilities this build has (D-63).
        saved_sessions: How many sessions are saved, or None when the saved list
            could not be read (D-172); which ones is never a fact.
    """

    app_version: str
    build_number: str | None
    python: str
    flet: str
    platform: str
    device: str | None
    os: str | None
    embedded: bool
    year: int
    source: Source
    feed_digest: bytes | None
    fetched_at: datetime | None
    zone: str
    device_offset: timedelta
    fake_clock_from: datetime | None
    now: datetime
    written_at: datetime
    custom_feed_url: bool
    reduced_motion: bool
    width: float | None
    capabilities: tuple[str, ...]
    saved_sessions: int | None


def diagnostics_text(facts: Facts) -> str:
    """Return the diagnostics text: one ``Name: value`` line per fact, 19 lines.

    Times are ISO 8601 in the conference's zone, with their offset, and the device's
    offset has an ASCII sign too ("UTC-07:00"). Every value is
    kept on one line and cut at ``MAX_VALUE`` characters, and its email addresses and
    URLs are written ``<email>`` and ``<url>``, so a value the app does not control
    (a device's model) cannot add a line or carry an address.

    Args:
        facts: What to say, from ``gather_facts()``.
    """
    zone = ZoneInfo(facts.zone)

    def moment(at: datetime) -> str:
        return at.astimezone(zone).isoformat(timespec="seconds")

    if facts.fetched_at is None:
        fetched = "never"
    else:
        fetched = (
            f"{moment(facts.fetched_at)} ({ago_label(facts.fetched_at, facts.now)})"
        )
    if facts.fake_clock_from is None:
        fake_clock = "off"
    else:
        fake_clock = f"from {moment(facts.fake_clock_from)}, now {moment(facts.now)}"
    lines = (
        ("App", facts.app_version),
        ("Build", facts.build_number or "none"),
        ("Python", facts.python),
        ("Flet", facts.flet),
        ("Device", facts.device or "unknown"),
        ("OS", facts.os or facts.platform),
        ("Run", "packaged app" if facts.embedded else NOT_EMBEDDED),
        ("Year", str(facts.year)),
        ("Schedule", _schedule_line(facts.source, facts.feed_digest)),
        ("Schedule fetched", fetched),
        ("Conference zone", facts.zone),
        ("Device offset", _offset_line(facts.device_offset)),
        ("Fake clock", fake_clock),
        ("Written", moment(facts.written_at)),
        ("Custom feed URL", "yes" if facts.custom_feed_url else "no"),
        ("Reduced motion", "on" if facts.reduced_motion else "off"),
        ("Width", _width_line(facts.width)),
        ("Capabilities", ", ".join(facts.capabilities) or "none"),
        ("Saved sessions", _saved_line(facts.saved_sessions)),
    )
    return "\n".join(f"{name}: {_clean(value)}" for name, value in lines)


async def gather_facts(
    page: ft.Page,
    *,
    info: ConferenceInfo,
    conference: Conference,
    prefs: Prefs,
    favorites: Favorites,
) -> Facts:
    """Read the facts the diagnostics text says, from the platform, the stores and the build.

    Asks the platform for the device (``page.get_device_info()``) and, in a packaged
    build, for its build (``read_build()``); when one fails, the text says "unknown" or
    "none" there and the rest is still read. Call it from an ``async``
    handler (D-70).

    Args:
        page: The session's page: its platform, width and device.
        info: The year's facts: its year and time zone.
        conference: The published schedule, its source, digest and age.
        prefs: The Developer options in effect and the OS's motion setting.
        favorites: The saved sessions, counted.
    """
    device, os_name = await _device_facts(page)
    build = await read_build(page)
    written_at = datetime.now(UTC)
    return Facts(
        app_version=build.version,
        build_number=build.number,
        python=platform.python_version(),
        flet=FLET_VERSION,
        platform=page.platform.value if page.platform else "unknown",
        device=device,
        os=os_name,
        embedded=is_embedded(),
        year=info.year,
        source=conference.source,
        feed_digest=conference.digest,
        fetched_at=conference.fetched_at,
        zone=info.time_zone,
        device_offset=written_at.astimezone().utcoffset() or timedelta(0),
        fake_clock_from=prefs.fake_now,
        now=clock.now(),
        written_at=written_at,
        custom_feed_url=prefs.feed_url is not None,
        reduced_motion=prefs.reduce_motion,
        width=page.width,
        capabilities=tuple(name for name, on in capabilities.ALL if on),
        saved_sessions=len(favorites.ids) if favorites.loaded else None,
    )


async def _device_facts(page: ft.Page) -> tuple[str | None, str | None]:
    """Return the device's make and model, and its OS, as the platform reports them.

    Only what names the kind of device: never its user-given name (an iPhone's is
    often a person's) or an identifier.

    Args:
        page: The session's page.

    Returns:
        The device and the OS, each None when the platform does not say: on another
        platform than Android and iOS, or when the call fails (logged by class).
    """
    try:
        info = await page.get_device_info()
    except SERVICE_ERRORS as error:
        logger.warning("Could not read the device info: %s", type(error).__name__)
        return None, None
    # Flet's device-info classes type as Any, so isinstance alone does not rule out None.
    if info is None:
        return None, None
    if isinstance(info, ft.AndroidDeviceInfo):
        kind = "" if info.is_physical_device else ", emulator"
        version = info.version
        return (
            f"{info.manufacturer} {info.model}{kind}",
            f"Android {version.release} (API {version.sdk})",
        )
    if isinstance(info, ft.IosDeviceInfo):
        kind = "" if info.is_physical_device else ", simulator"
        return f"{info.model_name}{kind}", f"{info.system_name} {info.system_version}"
    return None, None


def _schedule_line(source: Source, digest: bytes | None) -> str:
    """Return the schedule's line: where it came from and which feed it is.

    Args:
        source: ``Conference.source``.
        digest: ``Conference.digest``; its first ``_FEED_DIGITS`` hex digits name it.
    """
    if source == "none" or digest is None:
        return "none yet"
    return f"{source}, feed {digest.hex()[:_FEED_DIGITS]}"


def _offset_line(offset: timedelta) -> str:
    """Return the device's UTC offset in ISO 8601 with an ASCII sign, e.g. "UTC-07:00".

    Not ``timefmt.utc_offset_label()``, whose typographic minus suits the Developer
    screen but not text pasted into an issue: a search for "-07:00" or "UTC-" must
    find it, as it finds the other lines' ``isoformat()`` offsets. Zero is "UTC+00:00".

    Args:
        offset: ``Facts.device_offset``.
    """
    sign = "-" if offset < timedelta(0) else "+"
    minutes = abs(int(offset.total_seconds())) // 60
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def _width_line(dp: float | None) -> str:
    """Return the width line: the page's width and its Material window size class.

    Args:
        dp: The page's width, or None before Flutter reported it.
    """
    if dp is None:
        return "unknown"
    if dp < _MEDIUM_FROM:
        size = "compact"
    elif dp < _EXPANDED_FROM:
        size = "medium"
    else:
        size = "expanded"
    return f"{dp:.0f} dp, {size}"


def _saved_line(count: int | None) -> str:
    """Return the saved sessions' line: how many, or that the list could not be read.

    Args:
        count: ``Facts.saved_sessions``.
    """
    return "unknown (the saved list could not be read)" if count is None else str(count)


def _clean(value: str) -> str:
    """Return ``value`` on one line, cut at ``MAX_VALUE``, without emails or URLs.

    Args:
        value: A fact's value as written.
    """
    value = " ".join(value.split())
    value = EMAIL.sub(REDACTED_EMAIL, _URL.sub(_REDACTED_URL, value))
    if len(value) > MAX_VALUE:
        value = value[: MAX_VALUE - 1] + "…"
    return value
