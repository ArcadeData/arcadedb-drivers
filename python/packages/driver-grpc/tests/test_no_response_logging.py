"""Repository-level backstop for arcadedb#7309: no hand-written source file in this package may
use `logging`, `print`, or write to `sys.std{out,err}` directly.

This is the blunt half of the response-isolation guard - `test_auth_response_isolation.py` proves
the eight interceptor methods specifically never read anything off a response; this test instead
proves a wider, cruder claim: NOTHING in `src/arcadedb_driver_grpc/` (any file, any function,
today or after an unrelated edit) logs anything at all. A future change that started logging a
`CreateApiToken` response from `transaction.py` or `stream.py` - nowhere near the interceptors -
would slip past the interceptor-level test but fails this one.

What this does NOT prove: it cannot see a call built through indirection (`getattr(logging,
"info")(...)`, a module imported under an alias then invoked through a variable), or a call to a
third-party logger this package doesn't depend on today. It is a net over the source text, not a
data-flow analysis - a clean run is evidence of "no literal logging/print/stdout/stderr call
exists", not "no response ever reaches a log sink by any means".
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "arcadedb_driver_grpc"

# Matched by AST inspection rather than a substring/regex scan of the source text: a regex over
# "print(" would also flag a docstring or comment that happens to mention it (this module's own
# docstring above does), and AST inspection is barely more code than a regex would be here.
_FORBIDDEN_CALL_NAMES = {"print"}
_FORBIDDEN_MODULES = {"logging"}
_FORBIDDEN_ATTR_PATHS = {("sys", "stdout"), ("sys", "stderr")}


def _python_files_under(directory: Path) -> list[Path]:
    # `_generated` is excluded at the parent glob level (it lives under
    # `src/arcadedb_driver_grpc/_generated`, a sibling this walk does reach) because generated
    # code is never hand-edited and is not this test's concern - see the root CLAUDE.md.
    return [path for path in directory.rglob("*.py") if "_generated" not in path.parts]


def _offenses(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    offenses: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_MODULES:
                    offenses.append(f"{path}:{node.lineno}: imports {alias.name!r}")
        elif isinstance(node, ast.ImportFrom) and node.module in _FORBIDDEN_MODULES:
            offenses.append(f"{path}:{node.lineno}: imports from {node.module!r}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
            offenses.append(f"{path}:{node.lineno}: calls {node.func.id}(...)")
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and (node.value.id, node.attr) in _FORBIDDEN_ATTR_PATHS
        ):
            offenses.append(f"{path}:{node.lineno}: references {node.value.id}.{node.attr}")
    return offenses


def test_no_logging_print_or_direct_stdout_stderr_use() -> None:
    offenses = [offense for path in _python_files_under(SRC_DIR) for offense in _offenses(path)]
    assert not offenses, "found logging-shaped code:\n" + "\n".join(offenses)
