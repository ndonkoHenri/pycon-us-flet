"""Tests for the deep-link flow's default link, `maestro/subflows/open_link.yaml` (#518).

The flow takes the links' scheme and host from one env value, `LINK`, with a default
for runs that give none. That default must be the app's own: the one common
`[tool.flet.deep_linking]` table in `pyproject.toml` (D-269, D-452). If the scheme
or the host is renamed there, this check fails, so the default is changed with it
instead of the flow failing on a device with links the app no longer registers.
"""

import re
import tomllib
from pathlib import Path

from tests.ui.developer import ABOUT_APP_LINK

ROOT = Path(__file__).resolve().parent.parent
OPEN_LINK = ROOT / "maestro" / "subflows" / "open_link.yaml"

DEFAULT = re.compile(
    r"^- openLink: \$\{\(LINK \|\| '([^']+)'\) \+ ROUTE\}$", re.MULTILINE
)
"""The subflow's one `openLink`: LINK, else the default, then the route path."""


def flow_default() -> str:
    """Return the scheme and host the subflow uses when the run gives no `LINK`."""
    found = DEFAULT.findall(OPEN_LINK.read_text(encoding="utf-8"))
    assert len(found) == 1, "open_link.yaml has one openLink, LINK or its default"
    return found[0]


def app_link() -> str:
    """Return `<scheme>://<host>` from `pyproject.toml`'s deep-linking table."""
    with (ROOT / "pyproject.toml").open("rb") as file:
        table = tomllib.load(file)["tool"]["flet"]["deep_linking"]
    return f"{table['scheme']}://{table['host']}"


def test_the_flow_s_default_link_is_the_app_s_scheme_and_host() -> None:
    """D-269: the flow's default `LINK` equals `[tool.flet.deep_linking]`.

    A renamed scheme or host in `pyproject.toml` fails here, not on a device.
    """
    assert flow_default() == app_link()


def test_the_ui_flows_about_app_link_is_the_app_s() -> None:
    """D-478: the link `flet test` flows open uses `[tool.flet.deep_linking]`."""
    assert f"{app_link()}/more/app" == ABOUT_APP_LINK


def test_the_default_link_has_no_trailing_slash() -> None:
    """Each ROUTE starts with its own slash, so the default ends at the host."""
    assert not flow_default().endswith("/")
