"""The six goldens: Now, Schedule and Session detail, light and dark (D-78, §6).

One test, one launch: it sets the fake clock to a moment of the conference and the
recorded feed, then takes each screen in light and in dark, and compares the capture
with the committed image under `tests/ui/golden/<platform>/goldens/`.

What they protect against: an unintended change in how these three screens look, such
as a colour token, a spacing, a clipped or overflowing row, a dark theme that missed a
surface. They run at phase exits and Flet pin bumps, on the one emulator below, and a
failure means "look at the diff": an intended change is re-recorded with `-u` or
`--update-failed-goldens` (testing-and-quality.md §6). They say nothing about how a
phone draws the app: the emulator's fonts, density and compositor differ from a
phone's, so a pass here is no pass for the device checklist (§9).

Recorded on the Android emulator `pycon_pixel6a_api36` (Pixel 6a, 1080 x 2400 px,
420 dpi, API 36, animations off, SystemUI demo mode on). iOS has no goldens (§6).
"""

import asyncio
import subprocess

import flet.testing as ftt
import pytest
from flet.testing.remote_tester import RemoteTester

from tests.ui.developer import fresh_start, open_route
from tests.ui.helpers import (
    DEVICE,
    PLATFORM,
    STEP,
    adb,
    capture,
    demo_mode,
    open_tab,
    remote,
    tap_back_arrow,
    tap_id,
    wait_for_id,
    wait_for_tooltip,
)
from tests.ui.targets import conference_days, day_rows, recorded, row_id, saveable

SIMILARITY = 99.9
"""The threshold, in percent, of every comparison. `assert_screenshot`'s default, 99.0,
passes a background 20 levels darker (99.35) and a blanked 120 px band (99.14), because
structural similarity barely reacts to a uniform colour shift; 99.9 fails both. It sits
under the worst difference a run showed from a minute ticking over in the fake clock
(99.978) and the status bar's noise before the mobile icon was hidden (99.991), and 99.99
would fail on a slow launch (testing-and-quality.md §6)."""

AVD = "pycon_pixel6a_api36"
"""The Android virtual device the images were recorded on."""


def on_golden_device() -> bool:
    """Return whether this run's device is an emulator of `AVD`, the goldens' one.

    Checked when pytest collects the module, so a run of every flow on another device
    skips this test instead of failing six comparisons there: its fonts and density
    differ (testing-and-quality.md §6). A copy of the AVD on another port counts, as
    `tools/device.py` boots them read-only.
    """
    if PLATFORM != "android":
        return False
    name = subprocess.run(
        [adb(), "-s", DEVICE, "shell", "getprop", "ro.boot.qemu.avd_name"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    ).stdout.strip()
    return name == AVD


pytestmark = pytest.mark.skipif(
    not on_golden_device(), reason=f"the goldens are of the Android emulator {AVD}"
)

OPENING_DAY = 2
"""The conference's first main day, the third day: its first sessions are keynotes."""

SETTLE_SECONDS = 1.5
"""Real time a screen gets to finish drawing before it is captured: `RemoteTester.pump`
does not wait that long on a device (testing-and-quality.md §5.2)."""


def golden_now() -> str:
    """Return the fake clock for the goldens: 09:30 on the opening day, conference time.

    The second session of that morning is under way then, so Now has a session
    happening and a next one to show.
    """
    return f"{conference_days(recorded())[OPENING_DAY].isoformat()} 09:30"


async def settle(t: RemoteTester) -> None:
    """Let the screen finish drawing: Android's capture pumps no frame (§6)."""
    for _ in range(int(SETTLE_SECONDS / 0.3)):
        await asyncio.sleep(0.3)
        await t.pump(STEP)
    await t.pump_and_settle()


async def choose_appearance(t: RemoteTester, theme: str) -> None:
    """Pick Light or Dark in Settings and return to the Now root.

    Settings is below the fold of More, so its deep link opens it (`open_route()`);
    Back returns to the More root, under it.

    Args:
        t: The tester, on a tab root.
        theme: `light` or `dark`, the radio rows' identifier ending.
    """
    await open_tab(t, "more")
    await open_route("/more/settings")
    await wait_for_id(t, "more.title", gone=True)  # Settings has covered the root
    await tap_id(t, f"settings.appearance.{theme}")
    await t.pump(STEP)
    await tap_back_arrow(t)
    await wait_for_id(t, "more.title")
    await wait_for_tooltip(t, "Back", gone=True)  # the pop has finished
    await open_tab(t, "now")


async def test_goldens(flet_app: ftt.FletTestApp, feed_url: str) -> None:
    """Each of the six screens matches its recorded image: Now, Schedule, Session detail.

    Compared at `SIMILARITY`, with the status bar frozen.
    """
    t = remote(flet_app)
    opening = saveable(day_rows(recorded(), OPENING_DAY))[1]  # PSF Welcome, at 09:25
    async with demo_mode():
        await fresh_start(t, now=golden_now(), feed_url=feed_url)
        for theme in ("light", "dark"):
            await choose_appearance(t, theme)
            await wait_for_id(t, "now.title")
            await settle(t)
            flet_app.assert_screenshot(
                f"now_{theme}", await capture(t, f"now_{theme}"), SIMILARITY
            )

            await open_tab(t, "schedule")
            await wait_for_id(t, row_id("schedule", opening))
            await settle(t)
            flet_app.assert_screenshot(
                f"schedule_{theme}", await capture(t, f"schedule_{theme}"), SIMILARITY
            )

            await tap_id(t, row_id("schedule", opening))
            await wait_for_id(t, "schedule.title", gone=True)  # the push has finished
            await wait_for_id(t, "session.title")
            await settle(t)
            flet_app.assert_screenshot(
                f"session_{theme}", await capture(t, f"session_{theme}"), SIMILARITY
            )
            await tap_back_arrow(t)
            await wait_for_id(t, "schedule.title")
            await wait_for_tooltip(t, "Back", gone=True)  # the pop has finished
