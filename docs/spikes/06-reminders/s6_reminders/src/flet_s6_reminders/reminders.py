"""The S6Reminders service: a Python face for flutter_local_notifications 22.3.1."""

from dataclasses import dataclass
from datetime import datetime

import flet as ft


@dataclass
class TapEvent(ft.Event["S6Reminders"]):
    """A notification was tapped while the app was running."""

    id: int | None
    payload: str | None


@dataclass(frozen=True)
class LaunchDetails:
    """Whether a notification tap started the app, and which one."""

    launched_by_tap: bool
    id: int | None
    payload: str | None


@dataclass(frozen=True)
class Pending:
    """A notification the OS will show later."""

    id: int
    title: str | None
    body: str | None
    payload: str | None


@ft.control("S6Reminders")
class S6Reminders(ft.Service):
    """Schedule, list and cancel local notifications that fire with the app closed."""

    on_tap: ft.EventHandler[TapEvent] | None = None

    async def initialize(self) -> LaunchDetails:
        """Set the plugin up and return how the app was launched."""
        details = await self._invoke_method("initialize")
        return LaunchDetails(**details)

    async def request_permission(self) -> bool | None:
        """Ask the OS for notification permission (Android 13+ and iOS)."""
        return await self._invoke_method("request_permission")

    async def permission_status(self) -> dict[str, bool | None]:
        """Return ``enabled`` (notifications) and ``exact`` (Android exact alarms)."""
        return await self._invoke_method("permission_status")

    async def request_exact(self) -> bool | None:
        """Open Android's "Alarms & reminders" setting for this app."""
        return await self._invoke_method("request_exact")

    async def zoned_schedule(
        self,
        id: int,
        title: str,
        body: str,
        at: datetime,
        *,
        payload: str | None = None,
        exact: bool = False,
    ) -> str | None:
        """Show a notification at the aware instant ``at``, even with the app closed.

        Returns:
            None when scheduled, else the platform error code (for example
            ``exact_alarms_not_permitted``).
        """
        if at.tzinfo is None:
            raise ValueError("at must be timezone-aware")
        result = await self._invoke_method(
            "zoned_schedule",
            {
                "id": id,
                "title": title,
                "body": body,
                "at": at.isoformat(),
                "payload": payload,
                "exact": exact,
            },
        )
        return None if result["ok"] else result["code"]

    async def get_pending(self) -> list[Pending]:
        """Return the notifications scheduled but not shown yet."""
        pending = await self._invoke_method("get_pending")
        return [Pending(**p) for p in pending or []]

    async def get_shown(self) -> list[int]:
        """Return the ids of this app's notifications shown and not dismissed yet."""
        shown = await self._invoke_method("get_shown")
        return [i for i in shown or [] if i is not None]

    async def cancel_all(self) -> None:
        """Cancel every pending and shown notification of this app."""
        await self._invoke_method("cancel_all")

    async def cancel_all_pending(self) -> None:
        """Cancel every pending notification, leaving the ones already shown."""
        await self._invoke_method("cancel_all_pending")
