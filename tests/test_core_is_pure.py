"""Guard D-67: ``pycon_us.core`` is pure Python and never imports Flet.

Two complementary checks keep this simple and honest:

* a static scan finds ``flet`` / ``flet_*`` imports anywhere in a core module,
  including inside functions;
* a runtime check imports every core module in a fresh interpreter and asserts
  that no Flet module got loaded, which also catches transitive imports
  (e.g. ``from .. import state``) and dynamic ones at import time.
"""

import ast
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "pycon_us" / "core"


def is_flet(module: str) -> bool:
    """Return whether ``module`` is Flet itself or a Flet extension package."""
    top = module.split(".")[0]
    return top == "flet" or top.startswith("flet_")


def imported_modules(path: Path) -> set[str]:
    """Return the absolute module names that ``path`` imports statically.

    ``from a import b`` gives both ``a`` and ``a.b``, since ``b`` may be a submodule
    (``from pycon_us.core import html_md``); a name that is not one does no harm.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_core_never_imports_flet_statically() -> None:
    offenders = {
        str(path.relative_to(CORE)): sorted(
            name for name in imported_modules(path) if is_flet(name)
        )
        for path in sorted(CORE.rglob("*.py"))
    }
    assert {path: names for path, names in offenders.items() if names} == {}


def test_importing_core_loads_no_flet_module() -> None:
    modules = ["pycon_us.core"] + [
        "pycon_us.core." + ".".join(path.relative_to(CORE).with_suffix("").parts)
        for path in sorted(CORE.rglob("*.py"))
        if path.name != "__init__.py"
    ]
    probe = (
        "import importlib, sys\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'flet' or m.startswith('flet_'))\n"
        "print(','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_static_scan_sees_both_import_forms(tmp_path: Path) -> None:
    module = tmp_path / "sample.py"
    module.write_text(
        "import flet as ft\nfrom flet_map import Map\nimport json\n", encoding="utf-8"
    )
    assert {name for name in imported_modules(module) if is_flet(name)} == {
        "flet",
        "flet_map",
        "flet_map.Map",
    }


def test_static_scan_sees_a_submodule_imported_from_its_package(tmp_path: Path) -> None:
    module = tmp_path / "sample.py"
    module.write_text("from pycon_us.core import html_md\n", encoding="utf-8")
    assert "pycon_us.core.html_md" in imported_modules(module)
