"""Helpers for the UI flows. They drive the app only through its own UI (D-78).

``flet test`` always runs in device mode: the app runs on the emulator or simulator, and
the flow drives it through ``flet_app.tester``, a ``RemoteTester``. That tester finds
controls and taps them, but cannot drag, scroll or tap at a point (F21), and a
``Finder`` only counts matches (testing-and-quality.md §5.1, §13). So the helpers poll
with ``pump()`` until a finder matches (or stops matching), and flows tap by finder.
"""

import asyncio
import os
import shutil
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import flet as ft
import flet.testing as ftt
from flet.testing import Finder
from flet.testing.remote_tester import RemoteTester

STEP = ft.Duration(milliseconds=100)
"""How long each poll lets the app run before looking again."""

TIMEOUT = 15.0
"""Seconds a step may take: a debug build on an emulator is slow, never this slow."""

START_TIMEOUT = 180.0
"""Seconds from launch to Now. Each run installs the test build afresh, so its first
launch unpacks Python before it starts, slowly on a busy host's emulator."""

RETAP_SECONDS = 1.0
"""How long ``tap_until`` waits for a tap's effect before it taps again."""

PLATFORM = os.environ.get("FLET_TEST_PLATFORM", "")
"""``android`` or ``ios``, set by ``flet test``."""

DEVICE = os.environ.get("FLET_TEST_DEVICE", "")
"""The emulator's or simulator's id, ``flet test``'s ``-d``."""

SCREENSHOTS = Path("build") / "ui" / PLATFORM
"""Where ``screenshot()`` saves each step's image; ``flet test`` runs from the repo root."""


def remote(flet_app: ftt.FletTestApp) -> RemoteTester:
    """Return the app's tester, which ``flet test`` makes a ``RemoteTester`` (D-78)."""
    tester = flet_app.tester
    assert isinstance(tester, RemoteTester), "UI flows run with flet test (device mode)"
    return tester


async def wait_for(
    t: RemoteTester,
    find: Callable[[], Awaitable[Finder]],
    what: str,
    *,
    gone: bool = False,
    count: int | None = None,
    timeout: float = TIMEOUT,
) -> Finder:
    """Pump frames until ``find()`` matches a control, or matches none when ``gone``.

    Args:
        t: The tester.
        find: Runs a finder, e.g. ``lambda: t.find_by_text("More")``.
        what: The control, for the failure message.
        gone: Wait for the control to leave the screen instead (a covered View is
            offstage once its push has finished, so finders skip it).
        count: Wait for exactly this many matches instead.
        timeout: Seconds before the step fails.

    Returns:
        The last finder.
    """
    expected = 0 if gone else count
    deadline = time.monotonic() + timeout
    while True:
        finder = await find()
        matched = finder.count > 0 if expected is None else finder.count == expected
        if matched:
            return finder
        if time.monotonic() > deadline:
            await screenshot_on_failure()
            wanted = "at least 1" if expected is None else str(expected)
            raise AssertionError(
                f"{what}: {finder.count} on screen, not {wanted}, after {timeout} s"
            )
        await t.pump(STEP)


async def wait_until(
    t: RemoteTester, met: Callable[[], bool], what: str, *, timeout: float = TIMEOUT
) -> None:
    """Pump frames until ``met()`` holds: for what the host sees, not the screen.

    For example a request that reached a fixture's server (``SilentFeed.requests``).

    Args:
        t: The tester.
        met: The condition, e.g. ``lambda: feed.requests > asked``.
        what: What is awaited, for the failure message.
        timeout: Seconds before the step fails.
    """
    deadline = time.monotonic() + timeout
    while not met():
        if time.monotonic() > deadline:
            await screenshot_on_failure()
            raise AssertionError(f"{what}: not after {timeout} s")
        await t.pump(STEP)


async def wait_for_id(
    t: RemoteTester, identifier: str, *, gone: bool = False, timeout: float = TIMEOUT
) -> Finder:
    """Wait for a control with this semantics identifier (``<screen>.<element>``)."""
    return await wait_for(
        t,
        lambda: t.find_by_semantics_identifier(identifier),
        f"identifier {identifier!r}",
        gone=gone,
        timeout=timeout,
    )


async def wait_for_text(
    t: RemoteTester, text: str, *, gone: bool = False, timeout: float = TIMEOUT
) -> Finder:
    """Wait for a control showing exactly this text."""
    return await wait_for(
        t, lambda: t.find_by_text(text), f"text {text!r}", gone=gone, timeout=timeout
    )


async def wait_for_tooltip(
    t: RemoteTester, tooltip: str, *, gone: bool = False, timeout: float = TIMEOUT
) -> Finder:
    """Wait for a control with this tooltip: an icon button's accessible name (D-27)."""
    return await wait_for(
        t,
        lambda: t.find_by_tooltip(tooltip),
        f"tooltip {tooltip!r}",
        gone=gone,
        timeout=timeout,
    )


async def tap(t: RemoteTester, finder: Finder) -> None:
    """Tap the first control the finder matched, and let the tap be handled."""
    await t.tap(finder.first)
    await t.pump(STEP)


async def tap_id(t: RemoteTester, identifier: str) -> None:
    """Tap the first control with this identifier, once it is on screen."""
    await tap(t, await wait_for_id(t, identifier))


async def tap_text(t: RemoteTester, text: str) -> None:
    """Tap the first control showing exactly this text, once it is on screen."""
    await tap(t, await wait_for_text(t, text))


async def open_tab(t: RemoteTester, tab: str) -> None:
    """Show a tab's root from another root, and wait until the switch has finished.

    Each root has its own bar (D-144), and while one root replaces another both bars
    are on screen: a tap on the leaving one is lost (#108 lost a My schedule tap that
    way on the iOS simulator, and a More tap on the Android emulator while Now
    re-rendered for a new fake clock). So the tab is tapped once one bar shows, and
    again every ``RETAP_SECONDS`` until its root's title shows (a tap on the tab
    already shown only scrolls its root to the top, D-166); the switch is over when
    the title shows with one bar again (D-170).

    Args:
        t: The tester, on a tab root.
        tab: The tab's key, as in ``app.nav.<tab>`` and ``<tab>.title``, e.g.
            ``my_schedule``.
    """
    nav = f"app.nav.{tab}"

    async def one_bar() -> Finder:
        return await wait_for(
            t, lambda: t.find_by_semantics_identifier(nav), f"one {nav}", count=1
        )

    await one_bar()
    await tap_until(
        t,
        lambda: t.find_by_semantics_identifier(nav),
        lambda: t.find_by_semantics_identifier(f"{tab}.title"),
        f"the {tab} tab",
    )
    await one_bar()


async def tap_tooltip(t: RemoteTester, tooltip: str) -> None:
    """Tap the first control with this tooltip, an icon button's name (D-27), once shown."""
    await tap(t, await wait_for_tooltip(t, tooltip))


async def tap_until(
    t: RemoteTester,
    target: Callable[[], Awaitable[Finder]],
    done: Callable[[], Awaitable[Finder]],
    what: str,
    *,
    timeout: float = TIMEOUT,
) -> None:
    """Tap ``target`` until ``done()`` matches: for a tap an animation can swallow.

    A SnackBar's action slides in for 250 ms, and a tap on it before it has arrived
    is lost (#197). Rather than wait a fixed time, the tap is repeated, every
    ``RETAP_SECONDS`` while its effect has not shown, until it shows. A tap on a list
    that is still scrolling only stops the scroll, the same way. Only for a target
    that acts once, as a SnackBar's action does, or whose second tap changes
    nothing, as Developer's Apply of the same values.

    Args:
        t: The tester.
        target: Finds the control to tap, e.g. ``lambda: t.find_by_text("Undo")``.
        done: Finds what the tap brings, e.g. the row an Undo restores.
        what: The step, for the failure message.
        timeout: Seconds before the step fails.
    """
    deadline = time.monotonic() + timeout
    retap_at = 0.0
    while not (await done()).count:
        now = time.monotonic()
        if now > deadline:
            await screenshot_on_failure()
            raise AssertionError(f"{what}: no effect after {timeout} s of taps")
        if now >= retap_at:
            finder = await target()
            if finder.count:
                await t.tap(finder.first)
                retap_at = now + RETAP_SECONDS
        await t.pump(STEP)


async def enter_text_id(t: RemoteTester, identifier: str, text: str) -> None:
    """Replace the text of the field with this identifier, as typing it would.

    ``RemoteTester.enter_text`` focuses the field (its ``TextField`` under the
    identifier's node) and hands it the whole text at once, so ``on_change`` runs once.
    """
    await t.enter_text((await wait_for_id(t, identifier)).first, text)
    await t.pump(STEP)


async def tap_first_text(t: RemoteTester, texts: Sequence[str]) -> None:
    """Tap the first of these texts that is on screen, once one of them is.

    For rows a feed refresh may change: the flow passes a few likely ones, so a new
    or a withdrawn entry does not fail it.
    """
    assert texts, "at least one text"

    async def find() -> Finder:
        finders = [await t.find_by_text(text) for text in texts]
        return next((finder for finder in finders if finder.count), finders[-1])

    await tap(t, await wait_for(t, find, f"any of the texts {list(texts)!r}"))


async def tap_back_arrow(t: RemoteTester) -> None:
    """Tap the app bar's back arrow, the Material one on both platforms (D-10).

    It waits until one arrow shows: while a push or a pop runs, the View on its way
    out shows its arrow too, and a tap that lands there is lost.
    """
    arrows = await wait_for(
        t, lambda: t.find_by_tooltip("Back"), "tooltip 'Back'", count=1
    )
    await tap(t, arrows)


async def press_system_back(t: RemoteTester) -> None:
    """Press Android's Back key, which the app gets as a view pop (D-17, D-141).

    ``RemoteTester`` cannot send it, so ``adb`` does, on the device ``flet test``
    targets. iOS has no Back key; its edge swipe needs a drag (F21) and stays a manual
    check (testing-and-quality.md §9).
    """
    assert PLATFORM == "android", "the system Back key is Android's"
    await run(adb(), "-s", DEVICE, "shell", "input", "keyevent", "KEYCODE_BACK")
    await t.pump(STEP)


async def screenshot(name: str) -> None:
    """Save the screen as ``build/ui/<platform>/<name>.png``, a record of the step.

    Not a golden: nothing compares it (goldens arrive in P4, testing-and-quality.md §6).
    The device's own tools take it: ``RemoteTester.take_screenshot`` works once per run
    on Android, where its second call fails ("Surface already converted to an image").
    """
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS / f"{name}.png"
    if PLATFORM == "android":
        path.write_bytes(await run(adb(), "-s", DEVICE, "exec-out", "screencap", "-p"))
    else:
        await run("xcrun", "simctl", "io", DEVICE, "screenshot", str(path))


async def screenshot_on_failure() -> None:
    """Save ``timed-out-<flow>.png``, what the screen showed instead, if the device lets us.

    Named after the flow (pytest's ``PYTEST_CURRENT_TEST``), so a run with several
    failures keeps each one's picture. A step often times out because the app or the
    device went away, and then ``adb`` or ``simctl`` fails too: that failure must not
    hide the step's own message.
    """
    current = os.environ.get("PYTEST_CURRENT_TEST", "")
    flow = current.split("::")[-1].split(" ")[0] or "flow"
    try:
        await screenshot(f"timed-out-{flow}")
    except (AssertionError, OSError) as error:
        print(f"No timed-out-{flow}.png: {error}")


async def run(*command: str) -> bytes:
    """Run a host command without blocking the tester's socket; return its output."""
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE
    )
    output, _ = await process.communicate()
    assert process.returncode == 0, f"{command[0]} failed: {' '.join(command)}"
    return output


def adb() -> str:
    """Return ``adb``: on ``PATH``, else in ``$ANDROID_HOME`` or Android Studio's SDK."""
    sdk = os.environ.get("ANDROID_HOME") or str(Path.home() / "Library/Android/sdk")
    return shutil.which("adb") or str(Path(sdk) / "platform-tools" / "adb")
