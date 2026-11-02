"""Door check's attendee-list preload: the hook that loads it and the line that says how.

Once a session is chosen, ``use_preload()`` loads who bought it
(``door_inventory.load_inventory()``) in a coroutine effect that Flet cancels on
unmount and when the session changes (D-70), so no call completes into a screen that
has gone. Scanning waits for it ("Loading attendee list… 2 of 5", DOOR-03). Then
``status_line()``, under the session chip, says "Ready, works offline · 128 attendees",
or "Badges will be checked online" with Retry when any session's call failed; scanning
starts either way (unknown badges go online, #766).

The list holds names, dietary needs and allergies: it lives in this hook's state
only, keyed by the account, the sessions and the try, so it goes when Door check
unmounts (leaving the tool, a sign-out) and when the session changes, and nothing
writes it anywhere (D-56).
"""

from dataclasses import dataclass
from typing import cast

import flet as ft

from pycon_us.core.admission import Inventory, attendee_count
from pycon_us.core.door_sessions import SEPARATOR, DoorChoice
from pycon_us.door_inventory import Loaded, load_inventory
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import announce, named

LOADING = "Loading attendee list\N{HORIZONTAL ELLIPSIS}"
"""Why scanning is paused while the list loads, before the count (DOOR-03)."""

READY = "Ready, works offline"
ONLINE = "Badges will be checked online"
RETRY = "Retry"


@dataclass(frozen=True)
class Preload:
    """Where the attendee list's load is, for one account, choice and try.

    Attributes:
        key: The account, the product ids and the try it was loaded for; a load for
            another key never stands.
        done: How many sessions' calls have finished.
        total: How many there are.
        loaded: The list once every call has finished, or None while loading.
    """

    key: tuple[str, tuple[int, ...], int]
    done: int = 0
    total: int = 0
    loaded: Loaded | None = None

    @property
    def inventory(self) -> Inventory:
        """The list as loaded so far: empty while loading."""
        return self.loaded.inventory if self.loaded is not None else Inventory()


@dataclass(frozen=True)
class Preloading:
    """``use_preload()``'s answer: the load and how to try it again.

    Attributes:
        preload: Where the load is.
        retry: Loads the list again.
    """

    preload: Preload
    retry: ft.ControlEventHandler


def use_preload(owner: str, choice: DoorChoice | None) -> Preloading:
    """Load the chosen sessions' attendee list, and load it again on Retry.

    Call it on every render, with or without a choice (D-70): without one it loads
    nothing and drops the list it held.

    Args:
        owner: The signed-in account (``Account.owner``).
        choice: The session, or sessions, chosen, or None.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    held, set_held = ft.use_state(cast(Preload | None, None))
    tries, set_tries = ft.use_state(0)  # Retry loads again
    ids = choice.product_ids if choice is not None else ()
    key = (owner, ids, tries)

    @report_errors
    async def load() -> None:
        if not ids:
            set_held(None)  # no session: the list goes with it
            return
        set_held(Preload(key, total=len(ids)))

        @report_errors
        def progress(done: int, total: int) -> None:
            """Show how many sessions' calls have finished."""
            set_held(Preload(key, done, total))

        if svc.api is None:  # the URL went meanwhile; the route's guard follows
            loaded = Loaded(Inventory(), ids)
        else:
            loaded = await load_inventory(svc.api, ids, progress)
        set_held(Preload(key, len(ids), len(ids), loaded))

    ft.use_effect(load, [owner, ids, tries])  # a change cancels the load running
    preload = (
        held if held is not None and held.key == key else Preload(key, total=len(ids))
    )
    words = status_words(preload)

    @report_errors
    async def say() -> None:
        # VoiceOver has no live regions: iOS hears "Ready" or "online" this way.
        if not (prefs.announcements and preload.loaded is not None and ids):
            return
        if is_top_view(page.route, view_path):
            await announce(svc.semantics, spoken(words))

    ft.use_effect(say, [words])

    @report_errors
    def retry() -> None:
        set_tries(lambda last: last + 1)  # the latest try, not this render's

    return Preloading(preload, retry)


def status_words(preload: Preload) -> str:
    """Return what the line says: "Loading attendee list… 2 of 5", "Ready, …".

    The count is left out for a single session ("1 of 1" says nothing).

    Args:
        preload: Where the load is.
    """
    if preload.loaded is None:
        count = f" {preload.done} of {preload.total}" if preload.total > 1 else ""
        return LOADING + count
    if preload.loaded.failed:
        return ONLINE
    count = attendee_count(preload.loaded.inventory)
    return f"{READY}{SEPARATOR}{count:,} attendee" + ("" if count == 1 else "s")


def spoken(words: str) -> str:
    """Return the line as a screen reader says it: the middle dot as a pause."""
    return words.replace(SEPARATOR, ", ")


def status_line(
    preload: Preload, *, on_retry: ft.ControlEventHandler, live: bool
) -> ft.Control:
    """Return the line under the session chip: the list's state, and Retry on a failure.

    A small ring while loading; the words wrap (200 % text); Retry is a named 48 dp
    button (``door.preload.retry``).

    Args:
        preload: Where the load is.
        on_retry: Loads the list again.
        live: Whether the words are a live region (not where iOS announces).
    """
    words = status_words(preload)
    lead: list[ft.Control] = []
    if preload.loaded is None:
        lead.append(
            ft.Container(
                ft.ProgressRing(width=16, height=16, stroke_width=2), padding=4
            )
        )
    text = ft.Semantics(
        identifier="door.preload",
        container=True,
        live_region=live,
        label=spoken(words),
        exclude_semantics=True,  # the label says it, once
        content=ft.Text(
            words,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        expand=True,
    )
    trail: list[ft.Control] = []
    if preload.loaded is not None and preload.loaded.failed:
        trail.append(
            named("door.preload.retry", ft.TextButton(RETRY, on_click=on_retry))
        )
    return ft.Row(
        [*lead, text, *trail],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
