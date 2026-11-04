"""The faults the mock injects on demand, so conference Wi-Fi can be replayed (D-57).

A fault is switched on for the next request only (one-shot) or for every request until
it is cleared. `transport.py` and `server.py` take the transport faults around
`handle`, and `handle` takes `revoked` itself; the clock skew is
`MockState.skew`. Each fault and what it simulates is in `README.md` ("Faults").
"""

from dataclasses import dataclass, field
from typing import Literal

type Fault = Literal["connect", "timeout", "lost_response", "revoked"]
"""A fault's name, as tests and `--fault` spell it."""

FAULTS: tuple[Fault, ...] = ("connect", "timeout", "lost_response", "revoked")


@dataclass
class Faults:
    """The faults switched on now, each one-shot or kept until cleared.

    Attributes:
        on: Each fault switched on, mapped to whether it stays on until cleared
            (False: the next request it applies to takes it and turns it off).
    """

    on: dict[Fault, bool] = field(default_factory=dict)

    def inject(self, fault: Fault, *, until_cleared: bool = False) -> None:
        """Switch a fault on.

        Args:
            fault: The fault.
            until_cleared: Keep it for every request until `clear`; by default only
                the next request it applies to takes it.

        Raises:
            ValueError: The mock doesn't model this fault.
        """
        if fault not in FAULTS:
            raise ValueError(f"fault must be one of {FAULTS}, not {fault!r}")
        self.on[fault] = until_cleared

    def clear(self, fault: Fault | None = None) -> None:
        """Switch one fault off, or every fault when none is named."""
        if fault is None:
            self.on.clear()
        else:
            self.on.pop(fault, None)

    def take(self, fault: Fault) -> bool:
        """Say whether a fault hits this request, turning a one-shot fault off.

        Args:
            fault: The fault the caller is about to simulate.

        Returns:
            True when the fault is on; the caller then simulates it.
        """
        if fault not in self.on:
            return False
        if not self.on[fault]:
            del self.on[fault]
        return True
