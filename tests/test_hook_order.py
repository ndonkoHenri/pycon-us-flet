"""The hook guard: every hook runs on every render, in the same order (D-70 rule 4; #613).

Flet matches a component's hooks by their call order, so a hook that runs on one
render and not the next shifts every hook after it. #540's `use_margin()` called
`ft.use_view_path()` only from 600 dp: a rotation across 600 dp gave one screen a
`RefHook` where it had kept a subscription, and Flet's update loop stopped for the
session (#606, U111). The rule had only review to keep it; this test walks the source.

A hook is any call to a `use_*` name: Flet's (`ft.use_state()`) and the app's own
(`use_margin()`), which call hooks. The guard checks the bodies of components
(`@ft.component`) and of `use_*` functions, and flags a hook under an `if`, a
loop, a `match` case, a `try`, a conditional expression, the right side of
`and`/`or`, or a comprehension, and a hook after a `return` that may end the
body early. Nested functions are other scopes: a handler runs no hooks, and a nested
component is checked on its own.
"""

import ast
from pathlib import Path

import pycon_us

SRC = Path(pycon_us.__file__).parent
"""The app's package, `src/pycon_us`, every module of which the guard walks."""

FIXTURES = Path(__file__).parent / "fixtures" / "hooks"
"""Old code the guard must flag."""

SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
"""Nodes whose bodies run at another time than the enclosing body's."""


def is_hook(node: ast.Call) -> bool:
    """Whether a call is a hook's: `use_x()` or `module.use_x()`.

    Args:
        node: The call.
    """
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name.startswith("use_")


def runs_hooks(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether a function's body must call its hooks unconditionally.

    Args:
        func: The function.
    """
    if func.name.startswith("use_"):
        return True
    for decorator in func.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if getattr(target, "attr", getattr(target, "id", None)) == "component":
            return True
    return False


def returns(node: ast.AST) -> bool:
    """Whether a statement holds a `return` of its own body, not a nested function's.

    Args:
        node: The statement.
    """
    if isinstance(node, SCOPES):
        return False
    if isinstance(node, ast.Return):
        return True
    return any(returns(child) for child in ast.iter_child_nodes(node))


class Finder:
    """Collects the hooks of one body that may not run on every render."""

    def __init__(self) -> None:
        """Start with nothing found."""
        self.found: list[tuple[int, str]] = []

    def block(self, statements: list[ast.stmt], conditional: bool) -> None:
        """Visit a sequence of statements; those after a `return` are conditional.

        Args:
            statements: The block, in order.
            conditional: Whether the block itself may not run.
        """
        for statement in statements:
            self.visit(statement, conditional)
            conditional = conditional or returns(statement)

    def visit(self, node: ast.AST, conditional: bool) -> None:
        """Visit a node, recording each hook call reached while `conditional`.

        Args:
            node: A statement or an expression.
            conditional: Whether the node may not run on every render.
        """
        match node:
            case _ if isinstance(node, SCOPES):
                return
            case ast.Call() if conditional and is_hook(node):
                self.found.append((node.lineno, ast.unparse(node.func)))
            case ast.If():
                self.visit(node.test, conditional)
                self.block(node.body, True)
                self.block(node.orelse, True)
                return
            case ast.For() | ast.AsyncFor():
                self.visit(node.iter, conditional)
                self.block(node.body, True)
                self.block(node.orelse, True)
                return
            case ast.While():
                self.visit(node.test, True)
                self.block(node.body, True)
                self.block(node.orelse, True)
                return
            case ast.Match():
                self.visit(node.subject, conditional)
                for case in node.cases:
                    if case.guard is not None:
                        self.visit(case.guard, True)
                    self.block(case.body, True)
                return
            case ast.Try() | ast.TryStar():
                for part in (node.body, node.orelse, node.finalbody):
                    self.block(part, True)
                for handler in node.handlers:
                    self.block(handler.body, True)
                return
            case ast.With() | ast.AsyncWith():
                for item in node.items:
                    self.visit(item.context_expr, conditional)
                self.block(node.body, conditional)
                return
            case ast.IfExp():
                self.visit(node.test, conditional)
                self.visit(node.body, True)
                self.visit(node.orelse, True)
                return
            case ast.BoolOp():
                self.visit(node.values[0], conditional)
                for value in node.values[1:]:
                    self.visit(value, True)
                return
            case ast.ListComp() | ast.SetComp() | ast.DictComp() | ast.GeneratorExp():
                # Only the first iterable runs once; the rest runs once per item.
                first = node.generators[0].iter
                self.visit(first, conditional)
                for child in ast.iter_child_nodes(node):
                    parts = (
                        ast.iter_child_nodes(child)
                        if child is node.generators[0]
                        else [child]
                    )
                    for part in parts:
                        if part is not first:
                            self.visit(part, True)
                return
        for child in ast.iter_child_nodes(node):
            self.visit(child, conditional)


def conditional_hooks(source: str) -> list[str]:
    """The hooks in a module's components and `use_*` functions that may not run.

    Args:
        source: The module's Python source.

    Returns:
        `"<function>:<line> <hook>"` for each, in source order.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and runs_hooks(
            node
        ):
            finder = Finder()
            finder.block(node.body, False)
            found += [f"{node.name}:{line} {hook}" for line, hook in finder.found]
    return sorted(found, key=lambda entry: int(entry.split(":")[1].split()[0]))


def test_every_hook_in_the_app_runs_on_every_render() -> None:
    """No component or `use_*` function in `src/pycon_us` calls a hook conditionally."""
    found = [
        f"{path.relative_to(SRC)} {entry}"
        for path in sorted(SRC.rglob("*.py"))
        for entry in conditional_hooks(path.read_text())
    ]
    assert found == []


def test_the_guard_flags_540_s_use_margin() -> None:
    """The `and` that froze the app on a rotation (#606) fails the guard."""
    source = (FIXTURES / "use_margin_540.py.txt").read_text()
    assert conditional_hooks(source) == ["use_margin:17 ft.use_view_path"]


def test_the_guard_flags_a_hook_under_an_if_a_loop_or_after_an_early_return() -> None:
    """Each conditional form in a component is flagged; the unconditional hooks are not."""
    source = """
@ft.component
def Page(items, ready):
    first = ft.use_state(0)
    if ready:
        ft.use_effect(setup)
    else:
        use_margin(LIST)
    for item in items:
        ft.use_memo(item)
    rows = [use_row(item) for item in items]
    label = use_label() if ready else ""
    try:
        use_tokens()
    except KeyError:
        pass
    match ready:
        case True:
            use_prefs()
    if not items:
        return None
    last = ft.use_ref()
    return first, rows, label, last
"""
    flagged = [entry.split()[1] for entry in conditional_hooks(source)]
    assert flagged == [
        "ft.use_effect",
        "use_margin",
        "ft.use_memo",
        "use_row",
        "use_label",
        "use_tokens",
        "use_prefs",
        "ft.use_ref",
    ]


def test_the_guard_passes_unconditional_hooks_and_other_scopes() -> None:
    """Hooks at a body's top level, in an `if`'s test, in a `with` or in handlers pass."""
    source = """
@ft.memo
@ft.component
def Row(item):
    services = use_services()
    if use_layout().wide:
        pass
    with use_lock():
        size = use_size(item)

    def on_click(e):
        if e:
            use_dialog()

    return [cell for cell in use_cells(item) if cell]


def helper(ready):
    if ready:
        return use_anything()


@ft.component
def Empty():
    if False:
        return None
"""
    assert conditional_hooks(source) == []
