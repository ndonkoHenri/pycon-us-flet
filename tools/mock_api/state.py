"""The mock API's in-memory state, its seed, and what every endpoint shares (D-50, D-57).

``MockState`` holds the seeded accounts, sponsors, products and attendees, plus every
lead, note, redemption and incident the endpoints record, so tests can count how often
a capture was applied under each ``capture`` semantics. ``Call`` is one signed request
as an endpoint sees it, and ``Refused`` is how an endpoint answers with an error.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SEED = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mock" / "seed.json"
"""The seed every ``MockState`` starts from: fake data only."""

type Capture = Literal["idempotent", "non_idempotent"]
"""How the mock applies a repeated capture (D-57; README, Unknown)."""

CAPTURES: tuple[Capture, ...] = ("idempotent", "non_idempotent")

COC_DEDUPE = 60
"""Seconds within which an idempotent mock records one unforced incident per attendee."""


@dataclass
class Account:
    """A seeded account, with what ``authenticate`` returns and the favourites it syncs.

    Attributes:
        role: What the account is for (``attendee``, ``speaker``, ``sponsor``,
            ``staff``, ``coc`` or ``all``); only the seed and the tests read it.
        email: The sign-in email.
        password: The sign-in password (fake).
        nickname: The name ``authenticate`` returns.
        key: The API key the client sends as ``X-API-Key`` (fake).
        secret: The API secret the client signs with (fake).
        features: The role flags as the server sends them; a flag left out is absent
            from every reply, which the client must read as False.
        favorites: The session ids ``mobile_state`` keeps, always strings (D-42).
        sponsor_id: The sponsor a lead-retrieval account's leads go to, or None.
    """

    role: str
    email: str
    password: str
    nickname: str
    key: str
    secret: str
    features: dict[str, bool]
    favorites: list[str] = field(default_factory=list)
    sponsor_id: int | None = None


@dataclass(frozen=True)
class Sponsor:
    """A sponsor that leads can be captured for.

    Attributes:
        id: The sponsor's id.
        name: Its name as the server sends it, literal quotes included.
        booth_number: Its booth, or None (then left out of the reply).
        logo_url: Its logo, or None (then left out of the reply).
    """

    id: int
    name: str
    booth_number: str | None = None
    logo_url: str | None = None


@dataclass(frozen=True)
class Category:
    """A product category: sessions for the door, or swag (``/shirt|swag/i``).

    Attributes:
        id: The category's id.
        name: Its name.
    """

    id: int
    name: str


@dataclass(frozen=True)
class Product:
    """Something an attendee buys: a ticketed session or a piece of swag.

    Attributes:
        id: The product's id.
        name: Its name, e.g. ``"Wed May 13 9:00 AM - All about decorators"``.
        category: Its category's id.
    """

    id: int
    name: str
    category: int


@dataclass
class Attendee:
    """A seeded attendee with a badge ``access_code:validator`` (all fake).

    Attributes:
        id: The attendee's id (``attendee_id`` in ``fetch_products``).
        access_code: The badge's access code.
        validator: The badge's validator, the part after the ``:``.
        first_name: What a lead capture returns.
        full_name: The full name.
        nickname: The nickname.
        badge_name: The name printed on the badge.
        email: The email, at ``example.com``.
        violations: Code of Conduct incidents recorded before the mock started.
        dietary: Dietary needs, or ``""``.
        has_allergy: Whether the attendee has an allergy.
        allergy: The allergy, or ``""``.
        products: The quantity bought of each product, by product id.
    """

    id: int
    access_code: str
    validator: str
    first_name: str
    full_name: str
    nickname: str
    badge_name: str
    email: str
    violations: int = 0
    dietary: str = ""
    has_allergy: bool = False
    allergy: str = ""
    products: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Lead:
    """One lead row the mock recorded (a duplicate shows as a second row)."""

    sponsor_id: int
    access_code: str
    at: float


@dataclass(frozen=True)
class LeadNote:
    """One note the mock recorded for a captured lead."""

    sponsor_id: int
    access_code: str
    note: str
    at: float


@dataclass(frozen=True)
class Redemption:
    """One redemption of a product the mock recorded, from a door or swag payload."""

    access_code: str
    product_id: int
    quantity: int
    scanned_at: str


@dataclass(frozen=True)
class Incident:
    """One Code of Conduct incident the mock recorded."""

    access_code: str
    notes: str
    forced: bool
    at: float


@dataclass
class MockState:
    """Everything the mock remembers between requests, in memory.

    Attributes:
        year: The conference year served; requests for another year are 404.
        accounts: The accounts, looked up by email or by API key.
        now: The mock's clock, in seconds since the epoch. Tests inject a fixed one;
            the server can pass a skewed one.
        sponsors: The sponsors leads go to.
        categories: The product categories.
        products: The products, by id.
        attendees: The attendees, by access code.
        capture: ``idempotent`` applies a repeated capture once; ``non_idempotent``
            applies every request (D-57).
        leads: Every lead recorded, in order.
        notes: Every lead note recorded, in order.
        redemptions: Every redemption recorded, in order.
        redeem_replies: Under ``idempotent`` capture, the first reply to each redeem
            request, keyed by (access code, ``scanned_at``, products and quantities).
        incidents: Every Code of Conduct incident recorded, in order.
    """

    year: int
    accounts: list[Account]
    now: Callable[[], float] = time.time
    sponsors: list[Sponsor] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)
    products: dict[int, Product] = field(default_factory=dict)
    attendees: dict[str, Attendee] = field(default_factory=dict)
    capture: Capture = "idempotent"
    leads: list[Lead] = field(default_factory=list)
    notes: list[LeadNote] = field(default_factory=list)
    redemptions: list[Redemption] = field(default_factory=list)
    redeem_replies: dict[tuple[object, ...], object] = field(default_factory=dict)
    incidents: list[Incident] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Refuse a capture semantics the mock doesn't model."""
        if self.capture not in CAPTURES:
            raise ValueError(f"capture must be one of {CAPTURES}, not {self.capture!r}")

    @classmethod
    def from_seed(
        cls,
        path: Path = SEED,
        now: Callable[[], float] = time.time,
        capture: Capture = "idempotent",
    ) -> MockState:
        """Load a fresh state from a seed file in the README's shape.

        Args:
            path: The seed JSON file.
            now: The clock to use.
            capture: The capture semantics to serve.

        Returns:
            A state that shares nothing with any other.
        """
        seed = json.loads(path.read_text(encoding="utf-8"))
        attendees = []
        for entry in seed.get("attendees", []):
            bought = {int(pid): qty for pid, qty in entry.pop("products").items()}
            attendees.append(Attendee(**entry, products=bought))
        return cls(
            year=seed["year"],
            accounts=[Account(**entry) for entry in seed["accounts"]],
            sponsors=[Sponsor(**entry) for entry in seed.get("sponsors", [])],
            categories=[Category(**entry) for entry in seed.get("categories", [])],
            products={p["id"]: Product(**p) for p in seed.get("products", [])},
            attendees={a.access_code: a for a in attendees},
            capture=capture,
            now=now,
        )

    def attendee(self, access_code: object, validator: str | None = None) -> Attendee:
        """Find an attendee by badge, checking the validator when one is given.

        Args:
            access_code: The access code as sent.
            validator: The validator to check, or None to skip the check.

        Returns:
            The attendee.

        Raises:
            Refused: 404 for an unknown access code or a wrong validator.
        """
        found = (
            self.attendees.get(access_code) if isinstance(access_code, str) else None
        )
        if found is None:
            raise Refused(404, "Unknown attendee access code.")
        if validator is not None and validator != found.validator:
            raise Refused(404, "Wrong badge validator.")
        return found

    def product(self, product_id: int) -> Product:
        """Find a product by id.

        Raises:
            Refused: 404 for an unknown product.
        """
        found = self.products.get(product_id)
        if found is None:
            raise Refused(404, "Unknown product.")
        return found

    def category_name(self, product: Product) -> str:
        """The name of a product's category, the key replies group products by."""
        return next(c.name for c in self.categories if c.id == product.category)

    def redeemed(self, access_code: str, product_id: int) -> int:
        """How many of a product an attendee has redeemed so far."""
        return sum(
            r.quantity
            for r in self.redemptions
            if (r.access_code, r.product_id) == (access_code, product_id)
        )

    def violations(self, attendee: Attendee) -> int:
        """An attendee's incidents: the seeded ones plus those recorded since."""
        recorded = sum(i.access_code == attendee.access_code for i in self.incidents)
        return attendee.violations + recorded


class Refused(Exception):
    """A request the mock answers with an error status.

    Attributes:
        status: The HTTP status.
        body: The error body, ``{"code", "error"}`` unless an endpoint says otherwise.
    """

    def __init__(self, status: int, message: str, body: object = None) -> None:
        """Create the refusal.

        Args:
            status: The HTTP status.
            message: What went wrong; it never echoes the request, so it always
                serialises.
            body: The error body; None gives the 2019 shape ``{"code", "error"}``.
        """
        super().__init__(status, message)
        self.status = status
        self.body = {"code": status, "error": message} if body is None else body


@dataclass(frozen=True)
class Call:
    """One signed request, as an endpoint sees it once the signature checked out.

    Attributes:
        state: The mock's state; endpoints that write change it.
        account: The account the key belongs to.
        now: The time of this request, from ``state.now``.
        query: The query after ``?``, exactly as sent (``""`` when there is none).
        segment: The route's variable path segment as sent, or ``""``.
        body: The body bytes as sent.
    """

    state: MockState
    account: Account
    now: float
    query: str = ""
    segment: str = ""
    body: bytes = b""

    def require(self, *flags: str) -> None:
        """Let the request through only if the account has one of these flags.

        Raises:
            Refused: 403 when it has none: Ionic shows nothing for it, it only logs.
        """
        if not any(self.account.features.get(flag) for flag in flags):
            raise Refused(403, "This account's role can't use this endpoint.")
