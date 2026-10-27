"""Whether the app's window is in front, and whether it came back since a moment (D-372).

Another app's window over the app (the in-app browser, the share sheet, a maps app)
is no route of Flutter's `Navigator`, so nothing gives the screen reader's focus back
when it closes (F54, #302). ``ui.focus_back`` does, and needs to know when the app has
left and come back: the lifecycle handler (``app.start()``) calls ``leave()`` on
``inactive`` and ``come_back()`` on ``resume``. Android reports both for the share
sheet and for the browser (F192); iOS shows both over the app's own window, which stays
active, so there it never leaves.
"""

import asyncio


class Presence:
    """The app's window in front or not, as the lifecycle events say (D-372).

    Attributes:
        returns: How many times the app has come back to the front this session; a
            caller reads it before it opens another app's window (``back_since()``).
    """

    def __init__(self) -> None:
        """Start in front, as a session does."""
        self.returns = 0
        self._closed = False
        self._in_front = asyncio.Event()
        self._in_front.set()
        self._away = asyncio.Event()

    def leave(self) -> None:
        """Note that another window has come in front of the app's (``inactive``)."""
        self._in_front.clear()
        self._away.set()

    def come_back(self) -> None:
        """Note that the app's window is in front again (``resume``)."""
        self.returns += 1
        self._away.clear()
        self._in_front.set()

    def close(self) -> None:
        """Wake every waiter for good: the session has been replaced (D-147)."""
        self._closed = True
        self._away.set()
        self._in_front.set()

    async def back_since(self, returns: int, *, leave_within: float) -> bool:
        """Wait until the app has left and come back since ``returns`` was read.

        Args:
            returns: ``returns`` as read before the other window was asked for.
            leave_within: How long, in seconds, the app may take to leave once this
                is called. A window that has not come within it never came (a link
                with no app to open it), so nothing waits for a return that is not
                due; a later, unrelated return would find the user elsewhere.

        Returns:
            True once the app is back in front; False when it did not leave in time,
            or the session closed.
        """
        if self.returns == returns and not self._away.is_set():
            try:
                await asyncio.wait_for(self._away.wait(), leave_within)
            except TimeoutError:
                return False
        await self._in_front.wait()
        return not self._closed and self.returns > returns
