"""The local mock of the private PyCon API (D-50, NEW-08).

``state.py`` holds the in-memory ``MockState``; ``handlers.py`` the pure ``handle`` that
both the tests (through ``transport.py``) and the LAN server use, with the staff
endpoints in ``check_in.py``, ``conduct.py`` and ``leads.py``. ``README.md`` is the
contract. Nothing here is bundled into the app.
"""
