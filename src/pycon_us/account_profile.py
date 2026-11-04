"""What an account is made of: its role flags, its stored profile, and the API's replies.

The `Account` store (`account.py`) reads `authenticate`'s and `check_features`'
replies, and `pycon.account`, through these: each flag absent or not a boolean reads
as False (STORE-05), and `is_speaker` comes with sign-in only, as in Ionic
(`user-data.ts` 61-66, 182-192).
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

FLAGS = {
    "lead_retrieval": "lead_retrieval",
    "door_check_in": "door_check",
    "mask_violation": "mask_violation",
    "is_speaker": "is_speaker",
}
"""Each role flag's name in the API's `features` and its field in the store."""

REFRESHED = ("lead_retrieval", "door_check_in", "mask_violation")
"""The flags `check_features` refreshes: `is_speaker` comes with sign-in only
(STORE-05, `user-data.ts` 61-66)."""


@dataclass(frozen=True)
class Profile:
    """What `pycon.account` keeps: the account without its key and secret.

    Attributes:
        email: The account's email, as the server sent it.
        nickname: The name the app greets the user by.
        features: The role flags by their API name; an absent one is False.
    """

    email: str
    nickname: str
    features: dict[str, bool]

    @classmethod
    def parse(cls, value: object) -> Profile | None:
        """Read a stored or received account, or None when it isn't one.

        Args:
            value: `pycon.account`'s JSON object, or `authenticate`'s reply.

        Returns:
            The profile; flags that are absent or not booleans read as False
            (STORE-05).
        """
        if not isinstance(value, dict):
            return None
        email, nickname = value.get("email"), value.get("nickname")
        features = value.get("features")
        if not (isinstance(email, str) and email and isinstance(nickname, str)):
            return None
        if not isinstance(features, dict):
            return None
        return cls(
            email, nickname, {name: features.get(name) is True for name in FLAGS}
        )

    def stored(self) -> dict[str, Any]:
        """Return the JSON object `pycon.account` holds."""
        return {
            "email": self.email,
            "nickname": self.nickname,
            "features": self.features,
        }


def secrets_of(reply: object) -> tuple[str, str] | None:
    """Return `authenticate`'s key and secret, or None when either is missing."""
    if not isinstance(reply, dict):
        return None
    api_key, api_secret = reply.get("key"), reply.get("secret")
    if (
        isinstance(api_key, str)
        and api_key
        and isinstance(api_secret, str)
        and api_secret
    ):
        return api_key, api_secret
    return None


def refreshed_flags(reply: object) -> dict[str, bool] | None:
    """Return `check_features`' flags, an absent one False, or None for another reply."""
    features = reply.get("features") if isinstance(reply, dict) else None
    if not isinstance(features, dict):
        return None
    return {name: features.get(name) is True for name in REFRESHED}


def log_unexpected(task: asyncio.Task[None]) -> None:
    """Log a flag refresh that failed unexpectedly as soon as it ends (D-71).

    Without it, the error of a refresh nobody awaits would surface only when the
    finished task is garbage collected.
    """
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("Role flag refresh failed unexpectedly", exc_info=error)
