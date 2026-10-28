"""The app's modules import in any order, as a phone's first import does (#746).

The tests' own imports load ``pycon_us.services`` early, which hid an import cycle that
stopped every packaged build at start; a fresh interpreter imports ``pycon_us.app``
first, as ``main.py`` does.
"""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["pycon_us.app", "pycon_us.prefs"])
def test_the_module_imports_first_in_a_fresh_interpreter(module: str) -> None:
    """Imported before anything else, the module loads: no import cycle bites."""
    done = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
