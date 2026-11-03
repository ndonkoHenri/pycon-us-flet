"""``tools/README.md`` lists every tool, so an agent can find one without reading the guides."""

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
NOT_TOOLS = {"__init__.py", "README.md", "__pycache__"}


def test_every_tool_has_a_line() -> None:
    """Each script and folder directly in ``tools/`` is named in the index."""
    index = (TOOLS / "README.md").read_text(encoding="utf-8")
    missing = [
        path.name
        for path in TOOLS.iterdir()
        if path.name not in NOT_TOOLS
        and not path.name.startswith(".")
        and path.name not in index
    ]
    assert not missing, f"add these to tools/README.md: {missing}"


def test_every_line_has_a_tool() -> None:
    """Each tool the index names exists, so it can't outlive a deleted script."""
    index = (TOOLS / "README.md").read_text(encoding="utf-8")
    named = [
        part.strip("`")
        for line in index.splitlines()
        if line.startswith("| `")
        for part in line.split(" | ")[0].removeprefix("| ").split(", ")
    ]
    missing = [name for name in named if not (TOOLS / name).exists()]
    assert not missing, f"not in tools/: {missing}"
