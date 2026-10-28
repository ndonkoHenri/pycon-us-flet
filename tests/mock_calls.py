"""Helpers for the mock API's staff-endpoint tests: a seeded state and signed calls.

Each call is signed the way Ionic signs it (``core/signing.py``) over the exact path
and body bytes sent, so the tests exercise the signature check as well as the endpoint.
"""

import json

from pycon_us.core.signing import auth_headers, canonical_body
from tools.mock_api.handlers import handle
from tools.mock_api.state import Account, Capture, MockState

NOW = 1_780_000_000.0
"""The mock's fixed clock in these tests."""

BASE = "/2026/api/v1/"


class Clock:
    """A clock the test moves by hand; the mock reads it through ``MockState.now``."""

    def __init__(self, at: float = NOW) -> None:
        """Start the clock at ``at``."""
        self.at = at

    def __call__(self) -> float:
        """The time now."""
        return self.at


def state_at(capture: Capture = "idempotent", clock: Clock | None = None) -> MockState:
    """A fresh seeded state with this capture semantics and a hand-moved clock."""
    return MockState.from_seed(now=clock or Clock(), capture=capture)


def account(state: MockState, role: str) -> Account:
    """The seeded account with this role."""
    return next(a for a in state.accounts if a.role == role)


def call(
    state: MockState,
    method: str,
    endpoint: str,
    role: str = "",
    payload: object = None,
) -> tuple[int, object]:
    """Send one request to ``handle``, signed as ``role`` unless it is empty.

    Args:
        state: The mock's state.
        method: The HTTP method.
        endpoint: The path under ``/2026/api/v1/``, with its query as it is sent.
        role: The seeded account to sign as, or ``""`` to send no credentials.
        payload: The JSON body, serialised as ``JSON.stringify`` would, or None.

    Returns:
        The status and the decoded body.
    """
    path = f"{BASE}{endpoint}"
    body = b"" if payload is None else canonical_body(payload)
    headers: dict[str, str] = {}
    if role:
        who = account(state, role)
        signed = auth_headers(who.key, who.secret, state.now(), method, path, body)
        headers = {name: str(value) for name, value in signed.items()}
    status, _, reply = handle(state, method, path, headers, body)
    return status, json.loads(reply)
