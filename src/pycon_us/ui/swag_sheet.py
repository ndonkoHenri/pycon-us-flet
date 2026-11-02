"""The hand-out sheet: what a Swag pickup scan can take, pre-ticked, one tap away (#769).

ux.md §7.3 (SHIRT-03, SHIRT-04; O-7). Ionic's Redeem Products modal made staff tick
each item and reported in a toast; here a modal ``BottomSheet`` with a drag handle,
everything scrolling together so Hand out stays in reach at 200 % text, as the lead
note sheet (``ui/lead_note_sheet.py``):

- a level-1 heading "Hand out to Ada Example";
- per category, alphabetically, a level-2 heading and a ``Checkbox`` row per item,
  "2× T-Shirt (M)" (``swag.item.<product_id>``; the whole row toggles it, one stop
  read with its state). A product is all or nothing, as the API redeems it. Items
  left are ticked as the sheet opens; one picked up is disabled with "Picked up"
  under it, and one partly picked up says "1 already picked up";
- Cancel (``swag.cancel``) and ``FilledButton("Hand out 3 items")`` (``swag.hand_out``),
  whose words follow the ticks, disabled at none.

``use_swag_sheet()`` is Swag pickup's hook. Its ``offer`` opens the sheet for a
lookup's ``Offer`` and waits until it closes: Hand out sends ``swag.hand_out()`` once
(a ring and "Handing out…" meanwhile; a second tap sends nothing) and returns its
result for the panel; Cancel, Back or a swipe returns None and sends nothing.

Two client events need care. Flutter reports a sheet's dismissal after its exit
animation, which may be after the next attendee's sheet opened: each opening carries a
token, and a dismissal for another one is ignored. And the pinned Flet reads
``dismissible`` only as the sheet opens, so ``False`` while sending can't lock a sheet
already open: a scrim tap or Back while sending closes it on the client, but the
hand-out stays in progress (and scanning paused) until its answer settles it (#782).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us import swag
from pycon_us.core.badges import ScanResult
from pycon_us.core.check_in import Item
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import use_tokens
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.buttons import LABEL_PADDING, busy_label
from pycon_us.ui.queue_rows import heading
from pycon_us.ui.semantics import named

PICKED_UP = "Picked up"
SENDING = "Handing out…"
CANCEL = "Cancel"
"""The sheet's fixed words (ux.md §7.3)."""


@dataclass(frozen=True)
class Handing:
    """The offer the sheet is open for, and what is ticked.

    Attributes:
        offer: The lookup's offer.
        ticked: The product ids ticked; only items left can be.
        sending: Hand out was tapped and its answer hasn't come.
        opening: This opening's token, kept as the ticks change: a dismissal carries
            it, so a late one for an earlier sheet closes nothing.
    """

    offer: swag.Offer
    ticked: frozenset[int]
    sending: bool = False
    opening: object = field(default_factory=object, compare=False)

    @property
    def quantities(self) -> dict[int, int]:
        """What Hand out redeems: each ticked product's whole count, in the sheet's order."""
        return {i: n for i, n in self.offer.available.items() if i in self.ticked}


def hand_out_words(count: int) -> str:
    """Return the button's words: "Hand out 3 items", "Hand out 1 item"."""
    return f"Hand out {swag.items(count)}"


@dataclass(frozen=True)
class SheetActions:
    """What the sheet's controls call.

    Attributes:
        toggle: An item's checkbox, with its product id and new state.
        hand_out: Hand out.
        cancel: Cancel.
        dismissed: A dismissal (a swipe, Back, a tap on the scrim), with the token
            of the opening it closed.
    """

    toggle: Callable[[int, bool], object]
    hand_out: Callable[[], object]
    cancel: Callable[[], object]
    dismissed: Callable[[object], object]


def swag_sheet(
    handing: Handing,
    actions: SheetActions,
    *,
    high_contrast: bool = False,
    reduce_motion: bool = False,
) -> ft.BottomSheet:
    """Return the hand-out sheet for ``handing`` (ux.md §7.3).

    Args:
        handing: The offer and the ticks.
        actions: The handlers.
        high_contrast: HC is on screen: a 1 dp ``outline`` edge draws the sheet.
        reduce_motion: The sheet appears without its slide (D-34, D-173).
    """
    body: list[ft.Control] = [heading(f"Hand out to {handing.offer.name}", 1)]
    for category, group in handing.offer.products.items_by_category:
        body.append(heading(category, 2))
        body += [item_row(item, handing, actions.toggle) for item in group]
    count = sum(handing.quantities.values())
    body.append(
        ft.Container(
            ft.Row(
                [
                    named(
                        "swag.cancel",
                        ft.TextButton(
                            CANCEL,
                            on_click=actions.cancel,
                            disabled=handing.sending,
                        ),
                    ),
                    hand_out_button(count, handing.sending, actions.hand_out),
                ],
                alignment=ft.MainAxisAlignment.END,
                wrap=True,
                spacing=8,
                run_spacing=8,
            ),
            padding=ft.Padding.only(top=8),
        )
    )
    return ft.BottomSheet(
        ft.Container(  # 16 dp gutters (ux.md §3.6), clear of the home bar
            padding=ft.Padding.only(left=16, right=16, bottom=16),
            content=ft.Column(
                body,
                spacing=0,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
        show_drag_handle=True,
        scrollable=True,  # up to the screen's height: Hand out stays in reach at 200 %
        use_safe_area=True,
        dismissible=not handing.sending,  # read only as it opens, at the pin (#782)
        shape=hc_sheet_shape(high_contrast),
        on_dismiss=lambda _: actions.dismissed(handing.opening),
        animation_style=ft.AnimationStyle.no_animation() if reduce_motion else None,
    )


def item_row(
    item: Item, handing: Handing, on_toggle: Callable[[int, bool], object]
) -> ft.Control:
    """Return an item's checkbox row: one stop read with its words and state.

    A ``ListTile`` with a leading ``Checkbox``, as the consent's row: its title
    wraps at 200 % text and a tap anywhere toggles it. An item picked up is disabled
    and says so, so a screen reader says why.

    Args:
        item: The item, as the lookup read it.
        handing: The ticks, and whether the hand-out is being sent.
        on_toggle: Called with the product id and its new state.
    """
    left = item.redeemable > 0
    picked = item.purchased - item.redeemable
    reason = (
        PICKED_UP if not left else f"{picked} already picked up" if picked else None
    )
    disabled = not left or handing.sending

    @report_errors
    def changed(e: ft.Event[ft.Checkbox]) -> None:
        on_toggle(item.product_id, bool(e.control.value))

    return named(
        f"swag.item.{item.product_id}",
        ft.ListTile(
            leading=ft.Checkbox(
                value=left and item.product_id in handing.ticked,
                on_change=changed,
                disabled=disabled,
            ),
            title=f"{item.redeemable if left else item.purchased}× {item.name}",
            subtitle=reason,
            toggle_inputs=True,  # a tap anywhere on the row ticks it
            disabled=disabled,
            content_padding=ft.Padding.symmetric(horizontal=0),
        ),
    )


def hand_out_button(
    count: int, sending: bool, on_click: Callable[[], object]
) -> ft.Control:
    """Return Hand out: its count in words, a ring and "Handing out…" while it sends.

    The words change with the ring, so a screen reader says the busy state, as Sync
    now's; disabled at no item or while sending, it takes no second tap.

    Args:
        count: The items ticked, counting each product's quantity.
        sending: The hand-out is being sent.
        on_click: Sends it.
    """
    return named(
        "swag.hand_out",
        ft.FilledButton(
            content=busy_label(SENDING) if sending else ft.Text(hand_out_words(count)),
            icon=None if sending else ft.Icons.REDEEM_OUTLINED,
            on_click=on_click,
            disabled=sending or count == 0,
            style=ft.ButtonStyle(padding=LABEL_PADDING),
            elevation=0,  # M3's filled button lies flat (ui/buttons.py)
        ),
    )


@dataclass(frozen=True)
class SwagSheet:
    """What Swag pickup gets from ``use_swag_sheet()``.

    Attributes:
        offer: Opens the sheet for an offer; returns the hand-out's result, or None
            when it was cancelled (``swag.OfferHandler``).
        is_open: The sheet is open: the scan screen pauses scanning meanwhile.
    """

    offer: swag.OfferHandler
    is_open: bool


def use_swag_sheet() -> SwagSheet:
    """Keep the sheet's offer and ticks, show it while open; return what opens it.

    Call it on every render (D-70). The handlers read the ticks from a ref, since a
    render may not run between two events (#756). The ``offer`` call waits on a
    future the sheet's closing resolves; an unmount resolves it with None, and an
    offer after it (a lookup that answered late) returns None at once, so the scan
    screen's handler never hangs.
    """
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    handing, set_state = ft.use_state(not_handing)
    latest: MutableRef[Handing | None] = ft.use_ref(handing)
    pending: MutableRef[asyncio.Future[ScanResult | None] | None] = ft.use_ref(None)
    mounted = ft.use_ref(True)  # cleared on unmount: a late answer then sets nothing

    @report_errors
    def set_handing(value: Handing | None) -> None:
        latest.current = value
        if mounted.current:
            set_state(value)

    @report_errors
    def settle(result: ScanResult | None) -> None:
        """Hand ``result`` to the waiting ``offer`` call, if one waits."""
        waiting, pending.current = pending.current, None
        if waiting is not None and not waiting.done():
            waiting.set_result(result)

    @report_errors
    def unmount() -> None:
        """Mark the screen gone and let a waiting scan end with its lookup."""
        mounted.current = False
        if latest.current is None or not latest.current.sending:
            settle(None)  # a hand-out on its way settles it with its answer

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors  # a failure reads as a cancel: the lookup stays on the panel
    async def offer(given: swag.Offer) -> ScanResult | None:
        if not mounted.current:
            return None  # nothing would render the sheet, nor settle its future
        settle(None)  # one sheet at a time: the scan screen awaits one handler
        waiting = asyncio.get_running_loop().create_future()
        pending.current = waiting
        set_handing(Handing(given, frozenset(given.available)))
        return await waiting

    @report_errors
    def toggle(product_id: int, ticked: bool) -> None:
        current = latest.current
        if current is None or current.sending:
            return
        ids = current.ticked | {product_id} if ticked else current.ticked - {product_id}
        set_handing(replace(current, ticked=ids & current.offer.available.keys()))

    @report_errors
    async def hand_out() -> None:
        current = latest.current
        if current is None or current.sending or not current.quantities:
            return  # the single flight: a second tap sends nothing
        set_handing(replace(current, sending=True))
        result = None  # an unexpected failure still ends the scan (reported)
        try:
            result = await swag.hand_out(svc.api, current.offer, current.quantities)
        finally:
            set_handing(None)
            settle(result)

    @report_errors
    def cancel() -> None:
        current = latest.current
        if current is None or current.sending:
            return  # a hand-out on its way keeps the pause and settles with its answer
        set_handing(None)
        settle(None)

    @report_errors
    def dismissed(opening: object) -> None:
        current = latest.current
        if current is not None and current.opening is opening:
            cancel()  # else a late dismissal of a sheet already closed

    ft.use_dialog(
        swag_sheet(
            handing,
            SheetActions(toggle, hand_out, cancel, dismissed),
            high_contrast=tokens.high_contrast,
            reduce_motion=prefs.reduce_motion,
        )
        if handing is not None
        else None
    )
    return SwagSheet(offer, handing is not None)


def not_handing() -> Handing | None:
    """Return None: no sheet open, the hook's first state (a typed default)."""
    return None
