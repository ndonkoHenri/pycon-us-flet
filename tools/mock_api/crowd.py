"""Made-up attendees added after the seeded four, for a large CoC directory (#758).

`--attendees N` (`MockState.from_seed(attendees=N)`) adds N of them, so the name
search's 25-row cap and a directory of thousands can be tried on a device. They are
generated, not seeded: the same N gives the same attendees. Every name is invented,
every email is at `example.com`, and some names carry accents so that folding is
exercised (D-46).
"""

from typing import Any

FIRST = (
    "Alex", "Bea", "Chidi", "Dana", "Émile", "Farah", "Gus", "Hana", "Ivo", "Jun",
    "Kofi", "Lena", "Mateo", "Nia", "Oskar", "Priya", "Quinn", "Rosa", "Sven",
    "Tomás", "Uma", "Viktor", "Wren", "Xiu", "Yara", "Zoë",
)  # fmt: skip
"""First names: 26, so every letter starts one."""

LAST = (
    "Example", "Sample", "Placeholder", "Test", "Mock", "Fixture", "Stub", "Dummy",
    "Fake", "Demo", "Müller",
)  # fmt: skip
"""Last names: 11, coprime with 26, so 286 attendees pass before a full name repeats."""

INCIDENTS = (0, 0, 0, 0, 1, 2, 3, 5)
"""Prior incidents, by turns: most attendees have none, a few have several."""


def crowd(count: int, first_id: int) -> list[dict[str, Any]]:
    """Return `count` made-up attendees as seed entries, numbered from `first_id`.

    Each is in the seed file's shape, so `MockState.from_seed` reads it as it reads
    a seeded one. Attendee `n` has access code `MOCK<n:04>` and validator
    `v4l1d<n:02>`, as the seeded ones do, and no products.

    Args:
        count: How many to make.
        first_id: The first one's id and code number (5 after the seeded four).

    Returns:
        The entries, in order.
    """
    entries = []
    for n in range(first_id, first_id + count):
        first, last = FIRST[n % len(FIRST)], LAST[n % len(LAST)]
        entries.append(
            {
                "id": n,
                "access_code": f"MOCK{n:04}",
                "validator": f"v4l1d{n:02}",
                "first_name": first,
                "full_name": f"{first} {last}",
                "nickname": f"{first.lower()}{n}",
                "badge_name": first,
                "email": f"attendee{n}@example.com",
                "violations": INCIDENTS[n % len(INCIDENTS)],
                "products": {},
            }
        )
    return entries
