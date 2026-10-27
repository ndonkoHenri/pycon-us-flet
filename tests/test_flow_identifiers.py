"""Tests for the identifiers that the Maestro flows in ``maestro/`` tap (#348, D-252).

A Maestro flow finds a control by its semantics identifier (D-33), which reaches
Android as the node's resource id and iOS as its accessibility identifier. The app
bar's Search button had none: its icon now carries ``app.search`` in an unlabelled
``Semantics``, as the bottom bar's icons carry ``app.nav.<tab>`` (D-166), so the
button stays one node named by its tooltip (D-234).
"""

import flet as ft

from pycon_us.memory import ViewMemory
from pycon_us.ui.scaffold import search_button
from tests import chrome
from tests.chrome import merged_button
from tests.fake_page import FakePage

# The harness's fixture, under this module's name, where pytest looks it up.
page = chrome.page


def test_the_search_button_s_icon_carries_app_search_inside_its_merged_node(
    page: FakePage,
) -> None:
    """D-252: the identifier is in the merged node, beside the tooltip that names it.

    The ``Semantics`` sits in the icon, under the ``MergeSemantics`` that ``merged()``
    puts straight around the button (F55), so it adds no node: the button is still one
    stop named "Search", and that node carries ``app.search``.
    """
    button = merged_button(search_button(ViewMemory(), "all"))
    assert button.tooltip == "Search"
    icon = button.icon
    assert isinstance(icon, ft.Semantics)
    assert icon.identifier == "app.search"
    assert icon.label is None  # no words of its own: the tooltip names the node
    assert icon.content == ft.Icon(ft.Icons.SEARCH)
