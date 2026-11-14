"""The `Layout` store: the window's width class and its room for content (D-09).

From 600 dp wide, M3's medium window class, tab roots show a `NavigationRail` beside
the body instead of the bottom bar (ux.md §8): a tablet, a phone in landscape, an iPad
in Split View. `App` builds the store from `page.width` and `follow_width()` keeps
it in step with `page.on_resize`. The store holds the class, not the width: an
observable notifies only when a field's value changes (F5), so a resize within a class
re-renders nothing, and only a crossing re-renders the screens that read it.

It also holds the width the body has, the window's less its side insets, once that is
wider than `READING_DP`: from there the content widths cap the screens (`ui.widths`,
D-305). Under it no cap applies, so a phone in portrait still re-renders on nothing.

And it holds whether the window is short, under `SHORT_DP` tall: a phone in landscape,
where the keyboard leaves room for one field, so the scan screen leads with it (D-501).
"""

from dataclasses import dataclass

import flet as ft

from pycon_us.services.errors import report_errors

WIDE_DP = 600
"""The narrowest window, in dp, that shows the rail: M3's medium window class (D-09)."""

READING_DP = 720
"""The widest a reading screen's content may be, in dp (D-09): detail and info pages."""

LIST_DP = 840
"""The widest a list's content may be, in dp (D-09): every screen but reading ones."""

SHORT_DP = 480
"""The lowest window, in dp, that isn't short: M3's compact height class ends here.
A phone in landscape is about 400 dp tall, a tablet either way 800 or more (D-501)."""


def is_wide(width: float | None) -> bool:
    """Return whether a window `width` dp wide shows the rail rather than the bar.

    Args:
        width: The window's width in dp; None before Flutter has reported one (a
            test page), which counts as a phone.
    """
    return width is not None and width >= WIDE_DP


def is_short(height: float | None) -> bool:
    """Return whether a window `height` dp tall is short: a phone in landscape.

    Args:
        height: The window's height in dp; None before Flutter has reported one (a
            test page), which counts as not short.
    """
    return height is not None and 0 < height < SHORT_DP


# eq=False: a store is one object, compared by identity (F5), as the other stores.
@ft.observable
@dataclass(eq=False)
class Layout:
    """The window's width class, which decides the bar or the rail (D-277).

    No `reset()`: it holds a device fact, not a choice, as `Prefs`' device fields,
    which Reset app keeps (D-198).

    Attributes:
        wide: Whether the window is `WIDE_DP` wide or wider.
        room: The body's width in dp, the window's less its side insets (the
            `SafeArea`'s), when it is wider than `READING_DP`; else 0, since no
            content cap applies under it (D-305).
        short: Whether the window is under `SHORT_DP` tall (D-501). The window's
            height, not the body's: the keyboard leaves it as it is.
    """

    wide: bool = False
    room: float = 0.0
    short: bool = False

    def set_width(
        self, width: float | None, insets: float = 0.0, height: float | None = None
    ) -> None:
        """Take the window's new size; only a change of class or of `room` notifies.

        Args:
            width: The window's width in dp, from `page.width` or a resize.
            insets: The left and right safe-area insets together, in dp: a notch or a
                cutout beside the body in landscape (`page.media.padding`).
            height: The window's height in dp, from `page.height` or a resize.
        """
        self.wide = is_wide(width)  # the same value notifies nothing (F5)
        self.short = is_short(height)
        room = (width or 0.0) - insets
        self.room = room if room > READING_DP else 0.0


def side_insets(media: ft.PageMediaData | None) -> float:
    """Return the left and right safe-area insets together, in dp; 0 without media.

    Args:
        media: The page's media, `page.media`; None on a test page.
    """
    if media is None:
        return 0.0
    padding = media.padding
    return float(padding.left or 0) + float(padding.right or 0)


def layout_for(page: ft.Page) -> Layout:
    """Return a `Layout` of the page's first width, so the first screen has its layout.

    Flet has `page.width` and `page.media` before the session starts
    (`flet_backend.dart` registers the client only after the first size, D-277).

    Args:
        page: The session's page.
    """
    layout = Layout()
    layout.set_width(page.width, side_insets(page.media), page.height)
    return layout


def follow_width(page: ft.Page, layout: Layout) -> None:
    """Keep `layout` in step with the window: the app's one `page.on_resize`.

    It also reads `page.width` once, for a resize that came before the handler was
    set. Flutter sends a resize after a rotation, a Split View or multi-window change
    and a window drag, at most every 100 ms (`PageMedia`'s debouncer), and a media
    change when the insets change; Flutter sends the two separately, so each takes
    the other's last value from the page (D-305).

    Args:
        page: The session's page.
        layout: The session's `Layout` store.
    """

    @report_errors
    def resized(e: ft.PageResizeEvent) -> None:
        layout.set_width(e.width, side_insets(page.media), e.height)

    @report_errors
    def media_changed(_e: object) -> None:
        # The page's media is already the new one; the event's type is not an Event
        # at the pin, so the handler reads the page rather than the event.
        layout.set_width(page.width, side_insets(page.media), page.height)

    page.on_resize = resized
    page.on_media_change = media_changed
    layout.set_width(page.width, side_insets(page.media), page.height)


LayoutCtx: ft.ContextProvider[Layout | None] = ft.create_context(None)
"""Provides the session's `Layout`; `App` writes the provider out (D-69)."""


def use_layout() -> Layout:
    """Return the `Layout` store and re-render the caller when its class changes (F3).

    Raises:
        RuntimeError: No `LayoutCtx` provider is above the calling component.
    """
    layout = ft.use_context(LayoutCtx)
    if layout is None:
        raise RuntimeError("use_layout() needs a LayoutCtx provider above it")
    return layout
