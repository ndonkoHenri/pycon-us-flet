"""A stand-in for `flet-secure-storage`, for the credentials and Account tests (#684).

`MemoryKeystore` is the extension's `SecureStorage` with only its transport
replaced, as `tests/fakes.py`'s `MemoryPrefs` is SharedPreferences: the calls the
app makes, their arguments and the errors a platform reports go through Flet's own
service class. It records each write and removal in `journal`, so a test can see
when they happened.
"""

from typing import Any

from flet_secure_storage import SecureStorage


class MemoryKeystore(SecureStorage):
    """`SecureStorage` backed by a dict instead of the Android Keystore or keychain."""

    def init(self) -> None:
        """Start empty, with no failing method and nothing recorded."""
        self.values: dict[str, str] = {}
        self.failing: set[str] = set()  # the methods that raise, as a platform error
        self.journal: list[str] = []

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Answer `get`, `set` and `remove` from `values`.

        A method in `failing` raises the `RuntimeError` a platform error becomes
        (`Session.invoke_method`), with the call's arguments in its message, as
        Flet's does. Each write and removal is recorded as `"<method> <key>"`.
        """
        assert arguments is not None
        if method_name in self.failing:
            raise RuntimeError(f"PlatformException in {method_name}: {arguments}")
        key = arguments["key"]
        if method_name == "get":
            return self.values.get(key)
        self.journal.append(f"{method_name} {key}")
        if method_name == "set":
            self.values[key] = arguments["value"]
            return None
        if method_name == "remove":
            self.values.pop(key, None)
            return None
        raise AssertionError(f"unexpected call {method_name}")
