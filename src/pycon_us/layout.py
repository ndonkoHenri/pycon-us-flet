"""The ``Layout`` store: whether the window is wide enough for the rail (D-09, D-277).

From 600 dp wide, M3's medium window class, tab roots show a ``NavigationRail`` beside
the body instead of the bottom bar (ux.md §8): a tablet, a phone in landscape, an iPad
in Split View. ``App`` builds the store from ``page.width`` and ``follow_width()`` keeps
it in step with ``page.on_resize``. The store holds the class, not the width: an
observable notifies only when a field's value changes (F5), so a resize within a class
re-renders nothing, and only a crossing re-renders the screens that read it.
"""

from dataclasses import dataclass

import flet as ft

from pycon_us.services.errors import report_errors

WIDE_DP = 600
"""The narrowest window, in dp, that shows the rail: M3's medium window class (D-09)."""


def is_wide(width: float | None) -> bool:
    """Return whether a window ``width`` dp wide shows the rail rather than the bar.

    Args:
        width: The window's width in dp; None before Flutter has reported one (a
            test page), which counts as a phone.
    """
    return width is not None and width >= WIDE_DP


# eq=False: a store is one object, compared by identity (F5), as the other stores.
@ft.observable
@dataclass(eq=False)
class Layout:
    """The window's width class, which decides the bar or the rail (D-277).

    No ``reset()``: it holds a device fact, not a choice, as ``Prefs``' device fields,
    which Reset app keeps (D-198).

    Attributes:
        wide: Whether the window is ``WIDE_DP`` wide or wider.
    """

    wide: bool = False

    def set_width(self, width: float | None) -> None:
        """Take the window's new width; only a crossing of ``WIDE_DP`` notifies.

        Args:
            width: The window's width in dp, from ``page.width`` or a resize.
        """
        self.wide = is_wide(width)  # the same value notifies nothing (F5)


def follow_width(page: ft.Page, layout: Layout) -> None:
    """Keep ``layout`` in step with the window: the app's one ``page.on_resize``.

    It also reads ``page.width`` once, for a resize that came before the handler was
    set. Flutter sends a resize after a rotation, a Split View or multi-window change
    and a window drag, at most every 100 ms (``PageMedia``'s debouncer).

    Args:
        page: The session's page.
        layout: The session's ``Layout`` store.
    """

    @report_errors
    def resized(e: ft.PageResizeEvent) -> None:
        layout.set_width(e.width)

    page.on_resize = resized
    layout.set_width(page.width)


LayoutCtx: ft.ContextProvider[Layout | None] = ft.create_context(None)
"""Provides the session's ``Layout``; ``App`` writes the provider out (D-69)."""


def use_layout() -> Layout:
    """Return the ``Layout`` store and re-render the caller when its class changes (F3).

    Raises:
        RuntimeError: No ``LayoutCtx`` provider is above the calling component.
    """
    layout = ft.use_context(LayoutCtx)
    if layout is None:
        raise RuntimeError("use_layout() needs a LayoutCtx provider above it")
    return layout
