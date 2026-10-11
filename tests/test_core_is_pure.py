import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "pycon_us" / "core"


def imported_modules(path: Path) -> set[str]:
    """Return the top-level names of every module imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_core_never_imports_flet():
    """``pycon_us.core`` stays pure Python: no ``flet`` or ``flet_*`` imports (D-67)."""
    offenders = {
        str(path.relative_to(CORE)): sorted(
            name
            for name in imported_modules(path)
            if name == "flet" or name.startswith("flet_")
        )
        for path in sorted(CORE.rglob("*.py"))
    }
    assert {path: names for path, names in offenders.items() if names} == {}


def test_purity_check_detects_flet_imports(tmp_path):
    """The check above really sees both import forms."""
    module = tmp_path / "sample.py"
    module.write_text(
        "import flet as ft\nfrom flet_map import Map\nimport json\n", encoding="utf-8"
    )
    assert imported_modules(module) == {"flet", "flet_map", "json"}
