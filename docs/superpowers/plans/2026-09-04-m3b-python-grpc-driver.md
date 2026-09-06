# M3b: `arcadedb-driver-grpc` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `arcadedb-driver-grpc`, a Python client over ArcadeDB's gRPC data plane, with a sync and an async facade over one generated layer.

**Architecture:** protoc (via `grpcio-tools`) generates message and service modules from the committed `.proto` into `packages/driver-grpc/src/arcadedb_driver_grpc/_generated/`; `mypy-protobuf` generates their type stubs. Three hand-written wrappers - `stream_query`, `insert_stream`, `transaction` - sit on top in each of a sync (`__init__.py`) and an async (`aio.py`) flavour. Everything else is reached through the generated stub, exposed as `client.raw`.

**Tech Stack:** Python >= 3.10, uv workspace, grpcio, protobuf, grpcio-tools, mypy-protobuf, grpc-stubs, pytest, pytest-asyncio, testcontainers, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-04-m3b-python-grpc-driver-design.md`

## Global Constraints

- Run every command from `python/` unless a step says otherwise.
- Python floor is `>=3.10`. CI's unit job runs 3.10; the e2e job runs 3.14.
- `mypy` runs in **strict** mode over the whole package and its tests. No `# type: ignore` without a comment saying why.
- Generated code is **never** hand-edited. If output looks wrong, fix `generate-grpc.sh` or the contract.
- `ruff` line-length is 120. Lint selects `E, F, I, UP, B, SIM, RUF`.
- The package name is `arcadedb-driver-grpc` (PyPI) and `arcadedb_driver_grpc` (import). Version starts at `0.1.0`.
- The contract version in `[tool.arcadedb] server-version` must equal the committed contract's version - currently `26.9.1`. `scripts/adopt-contract-version.sh` rewrites it and **requires the key to appear exactly once** in the file.
- Test-only dependency on `arcadedb-driver` is allowed in the e2e suite. The runtime package must not depend on it.
- Commit after every task. Do not push or open a PR unless asked.

---

## File Structure

**New, at the repository root:**

| File | Responsibility |
|---|---|
| `scripts/resolve-proto-contract.sh` | Print the single `contracts/arcadedb-server-*.proto`, or fail loudly. |

**New, under `python/`:**

| File | Responsibility |
|---|---|
| `scripts/generate-grpc.sh` | Stage the contract under its package path, run protoc, write four files. |
| `packages/driver-grpc/pyproject.toml` | Package metadata, deps, `[tool.arcadedb] server-version`. |
| `packages/driver-grpc/README.md` | Public documentation and the compatibility table. |
| `packages/driver-grpc/LICENSE` | Copy of the repository's Apache-2.0 licence. |
| `.../src/arcadedb_driver_grpc/__init__.py` | Sync facade: `create_client`, `ArcadeDBGrpcClient`, public `__all__`. |
| `.../src/arcadedb_driver_grpc/aio.py` | Async facade: the same surface over `grpc.aio`. |
| `.../src/arcadedb_driver_grpc/auth.py` | `bearer_auth`, `password_auth`, the four-protocol channel interceptor. |
| `.../src/arcadedb_driver_grpc/errors.py` | `InsecureChannelError`. |
| `.../src/arcadedb_driver_grpc/stream.py` | `stream_query`, `insert_stream`, `InsertStreamRequest`. |
| `.../src/arcadedb_driver_grpc/transaction.py` | `Transaction`, `TransactionHandle`. |
| `.../src/arcadedb_driver_grpc/py.typed` | Marks the package as typed (empty file). |
| `.../src/arcadedb_driver_grpc/_generated/__init__.py` | Hand-written, empty package marker. protoc emits none. |
| `.../tests/conftest.py` | The in-process fake gRPC server fixture. |
| `.../tests/test_auth.py`, `test_client.py`, `test_stream.py`, `test_transaction.py`, `test_public_surface.py` | Unit tests. |
| `e2e/test_grpc.py`, `e2e/conftest_grpc.py` | End-to-end against a real container. |

**Modified:**

| File | Change |
|---|---|
| `python/pyproject.toml` | Workspace member is already `packages/*`; add dev deps, extend `mypy.files`. |
| `python/CLAUDE.md`, `CLAUDE.md`, `README.md` | Document the new package. |
| `.github/workflows/ci-python.yml` | Second drift gate. |
| `.github/workflows/publish-python.yml` | `package` input. |
| `.github/workflows/contract-watch.yml` | Regenerate the gRPC client too. |
| `scripts/tests/test-contract-scripts.sh` | Tests for the new resolver. |

---

### Task 1: `resolve-proto-contract.sh`

The proto twin of `resolve-openapi-contract.sh`. `generate-grpc.sh` (Task 2) must not glob for the contract, for the same reason the OpenAPI generator must not: a version bump puts two contracts side by side, and a glob picks by lexical order, which for `26.9.1` beside `26.9.2` is the **older** file.

**Files:**
- Create: `scripts/resolve-proto-contract.sh`
- Modify: `scripts/tests/test-contract-scripts.sh` (append a new section)

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/resolve-proto-contract.sh [contracts_dir]` - prints one absolute path on stdout, exits 0; exits 1 with diagnostics on stderr when the count is not exactly 1. Task 2 calls it.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/tests/test-contract-scripts.sh`, immediately before its final summary block (find the line that prints the PASS/FAIL totals and insert above it):

```bash
echo "resolve-proto-contract.sh"

# Exactly one proto: prints it, exits 0.
reset_fixture
out="$("$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" 2>/dev/null)"; rc=$?
check "$rc" "0" "exits 0 with exactly one proto"
check "$(basename "${out:-<none>}")" "arcadedb-server-26.9.1-SNAPSHOT.proto" "prints the single proto path"

# Two protos: refuses rather than picking one.
reset_fixture
touch "$FIX/contracts/arcadedb-server-26.9.2-SNAPSHOT.proto"
out="$("$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" 2>&1)"; rc=$?
check "$rc" "1" "refuses two protos instead of silently picking the older one"

# No proto at all: refuses.
reset_fixture
rm -f "$FIX"/contracts/arcadedb-server-*.proto
"$FIX/scripts/resolve-proto-contract.sh" "$FIX/contracts" >/dev/null 2>&1; rc=$?
check "$rc" "1" "refuses when no proto is present"
```

Then extend the fixture-copy line (around line 43) so the new script is present in the fixture. It currently reads:

```bash
  cp "$SCRIPTS_DIR/resolve-openapi-contract.sh" "$SCRIPTS_DIR/adopt-contract-version.sh" \
```

Add `"$SCRIPTS_DIR/resolve-proto-contract.sh"` to that list.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./scripts/tests/test-contract-scripts.sh`
Expected: FAIL - `cp: .../resolve-proto-contract.sh: No such file or directory`, or the three new checks report FAIL.

- [ ] **Step 3: Write the script**

Create `scripts/resolve-proto-contract.sh`:

```bash
#!/usr/bin/env bash
#
# Prints the path of the single contracts/arcadedb-server-*.proto, or fails.
#
# The proto twin of resolve-openapi-contract.sh, and it exists for the same
# reason: fetch-contract.sh names each contract after its version and writes the
# new one BESIDE the old, so a version bump transiently leaves two. A glob
# resolves those in lexical order, not version order - with 26.9.1 and 26.9.2
# side by side it yields 26.9.1, the STALE one - and nothing downstream notices,
# because the committed output does match the contract it was generated from,
# just not the current one.
#
# ci.yml already counts contracts/*.proto for the TypeScript pipeline. This
# script is what lets python/scripts/generate-grpc.sh refuse locally, before CI,
# and it is deliberately usable by ci.yml later.
#
# Prints the path on stdout so a caller can substitute it; diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACTS_DIR="${1:-$(cd "$SCRIPT_DIR/.." && pwd)/contracts}"

shopt -s nullglob
PROTOS=("$CONTRACTS_DIR"/arcadedb-server-*.proto)
shopt -u nullglob

if [[ "${#PROTOS[@]}" -eq 0 ]]; then
  echo "ERROR: no $CONTRACTS_DIR/arcadedb-server-*.proto found." >&2
  echo "Run scripts/fetch-contract.sh --proto-from <arcadedb checkout> <version> first." >&2
  exit 1
fi

if [[ "${#PROTOS[@]}" -ne 1 ]]; then
  echo "ERROR: expected exactly one $CONTRACTS_DIR/arcadedb-server-*.proto, found ${#PROTOS[@]}:" >&2
  printf '  %s\n' "${PROTOS[@]}" >&2
  echo "Generating from a glob would silently pick one by lexical order - for 26.9.1 beside" >&2
  echo "26.9.2 that is the OLDER file. Retire the superseded contract first:" >&2
  echo "  scripts/adopt-contract-version.sh <version>" >&2
  exit 1
fi

printf '%s\n' "${PROTOS[0]}"
```

- [ ] **Step 4: Make it executable and run the tests**

```bash
chmod +x scripts/resolve-proto-contract.sh
./scripts/tests/test-contract-scripts.sh
```

Expected: PASS, with the total three higher than before (39 rather than 36 if the suite was at 36).

- [ ] **Step 5: Commit**

```bash
git add scripts/resolve-proto-contract.sh scripts/tests/test-contract-scripts.sh
git commit -m "feat(scripts): resolve the single proto contract, or fail loudly"
```

---

### Task 2: Package scaffolding and codegen

Produces a package that imports and type-checks, with the four generated files committed. No facade yet.

**Files:**
- Create: `python/scripts/generate-grpc.sh`
- Create: `python/packages/driver-grpc/pyproject.toml`, `LICENSE`, `src/arcadedb_driver_grpc/__init__.py`, `src/arcadedb_driver_grpc/py.typed`, `src/arcadedb_driver_grpc/_generated/__init__.py`
- Modify: `python/pyproject.toml`

**Interfaces:**
- Consumes: `scripts/resolve-proto-contract.sh` from Task 1.
- Produces: `arcadedb_driver_grpc._generated.arcadedb_server_pb2` (all message classes, e.g. `StreamQueryRequest`, `QueryResult`, `GrpcRecord`, `InsertChunk`, `InsertSummary`, `BeginTransactionRequest`, `TransactionContext`) and `arcadedb_driver_grpc._generated.arcadedb_server_pb2_grpc` (`ArcadeDbServiceStub`, `ArcadeDbServiceAsyncStub`, `ArcadeDbServiceServicer`, `add_ArcadeDbServiceServicer_to_server`). Every later task imports from these two modules.

- [ ] **Step 1: Add the dependencies**

In `python/pyproject.toml`, add to `[dependency-groups] dev` (keep the list alphabetical):

```toml
    "grpc-stubs>=1.53.0.6",
    "grpcio-tools>=1.83.1",
    "mypy-protobuf>=3.6.0",
```

And extend `[tool.mypy] files` to cover the new package:

```toml
files = [
    "packages/driver/src/arcadedb_driver",
    "packages/driver/tests",
    "packages/driver-grpc/src/arcadedb_driver_grpc",
    "packages/driver-grpc/tests",
    "e2e",
]
```

`[tool.ruff] extend-exclude` already reads `["packages/*/src/*/_generated"]`, which matches the new path. Do not change it.

- [ ] **Step 2: Create the package skeleton**

```bash
mkdir -p packages/driver-grpc/src/arcadedb_driver_grpc/_generated packages/driver-grpc/tests
cp packages/driver/LICENSE packages/driver-grpc/LICENSE
touch packages/driver-grpc/src/arcadedb_driver_grpc/py.typed
```

Create `packages/driver-grpc/pyproject.toml`:

```toml
[project]
name = "arcadedb-driver-grpc"
version = "0.1.0"
description = "Python gRPC client for ArcadeDB's data plane, generated from ArcadeDB's protobuf contract."
readme = "README.md"
license = "Apache-2.0"
license-files = ["LICENSE"]
requires-python = ">=3.10"
keywords = ["arcadedb", "database", "graph-database", "multi-model", "grpc"]
dependencies = [
    "grpcio>=1.60",
    "protobuf>=4.25",
]

[project.urls]
Homepage = "https://github.com/ArcadeData/arcadedb-drivers/tree/main/python/packages/driver-grpc#readme"
Issues = "https://github.com/ArcadeData/arcadedb-drivers/issues"
Repository = "https://github.com/ArcadeData/arcadedb-drivers"

# The ArcadeDB server release this package was generated against. publish-python.yml
# re-verifies this against the committed contract's version before publishing, and
# scripts/adopt-contract-version.sh rewrites it on a contract bump - that script
# requires this key to appear EXACTLY ONCE in this file.
[tool.arcadedb]
server-version = "26.9.1"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/arcadedb_driver_grpc"]
```

Create `packages/driver-grpc/src/arcadedb_driver_grpc/_generated/__init__.py`:

```python
"""Package marker for the generated protobuf modules.

This is the one HAND-WRITTEN file inside a generated directory in this repository.
protoc emits no package marker of its own, and without this file the generated
modules are not importable as `arcadedb_driver_grpc._generated.*` from an
installed wheel.

It is intentionally empty and must stay that way: the drift gate diffs this whole
directory, so anything that changes here has to be reproducible by
`scripts/generate-grpc.sh`, and this file is not.
"""
```

Create a placeholder `packages/driver-grpc/src/arcadedb_driver_grpc/__init__.py`:

```python
"""Python gRPC client for ArcadeDB's data plane."""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
```

- [ ] **Step 3: Write the codegen script**

Create `python/scripts/generate-grpc.sh`:

```bash
#!/usr/bin/env bash
#
# Regenerates the gRPC client from the committed protobuf contract.
#
# Two things here are NOT arbitrary, and changing either produces output that is
# broken in a way the drift gate cannot see:
#
# 1. THE CONTRACT IS STAGED UNDER A NORMALISED FILENAME. protoc converts "-" to
#    "_" but treats "." as a DIRECTORY SEPARATOR. Handed
#    contracts/arcadedb-server-26.9.1.proto directly it writes
#    arcadedb_server_26/9/1_pb2.py and a service stub whose first import line is
#    `from arcadedb_server_26.9 import 1_pb2`, which is a SyntaxError - the output
#    cannot be imported at all. Staging it as `arcadedb_server.proto` sidesteps
#    that, and has the happy consequence that the generated module carries no
#    version stamp: nothing to retire on a contract bump, no imports to repoint.
#
# 2. THE STAGED PATH MIRRORS THE PYTHON PACKAGE PATH. protoc derives the generated
#    cross-file import from the proto's path relative to -I. Staged at the root,
#    the stub emits a bare `import arcadedb_server_pb2`, which resolves only if the
#    generated directory happens to be on sys.path. Staged at
#    arcadedb_driver_grpc/_generated/, it emits
#    `from arcadedb_driver_grpc._generated import arcadedb_server_pb2`, which is
#    correct for an installed wheel.
#
# --pyi_out is deliberately NOT passed: mypy-protobuf's --mypy_out writes the same
# arcadedb_server_pb2.pyi path with better stubs, and --mypy_grpc_out additionally
# types the service stub, which protoc does not do at all.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PYTHON_DIR/.." && pwd)"

PROTO="$("$REPO_ROOT/scripts/resolve-proto-contract.sh")"
PKG_DIR="$PYTHON_DIR/packages/driver-grpc/src"
REL_DIR="arcadedb_driver_grpc/_generated"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$REL_DIR"
cp "$PROTO" "$STAGE/$REL_DIR/arcadedb_server.proto"

cd "$PYTHON_DIR"
uv run python -m grpc_tools.protoc \
  -I"$STAGE" \
  --python_out="$PKG_DIR" \
  --grpc_python_out="$PKG_DIR" \
  --mypy_out="$PKG_DIR" \
  --mypy_grpc_out="$PKG_DIR" \
  "$REL_DIR/arcadedb_server.proto"
```

- [ ] **Step 4: Generate, and verify the output is importable**

```bash
chmod +x scripts/generate-grpc.sh
uv sync
./scripts/generate-grpc.sh
ls packages/driver-grpc/src/arcadedb_driver_grpc/_generated/
```

Expected: exactly five files - `__init__.py`, `arcadedb_server_pb2.py`, `arcadedb_server_pb2.pyi`, `arcadedb_server_pb2_grpc.py`, `arcadedb_server_pb2_grpc.pyi`.

Then prove it imports and that the async stub class exists:

```bash
uv run python -c "
from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as pb2_grpc
print(pb2.StreamQueryRequest, pb2.InsertChunk, pb2.InsertSummary)
print(pb2_grpc.ArcadeDbServiceStub, pb2_grpc.ArcadeDbServiceAsyncStub)
"
```

Expected: five class reprs, no traceback. **If the import raises `SyntaxError`, the staging in Step 3 is wrong** - re-read the comment block rather than editing the generated file.

- [ ] **Step 5: Lint and type-check**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Expected: all pass. If mypy reports errors inside `_generated`, do **not** add `follow_imports = "skip"` - `python/pyproject.toml` already explains why that erases the typing this plugin exists to provide. Add a scoped override instead:

```toml
[[tool.mypy.overrides]]
module = "arcadedb_driver_grpc._generated.*"
ignore_errors = true
```

- [ ] **Step 6: Commit**

```bash
cd .. && git add python/ scripts/ && git commit -m "feat(python-grpc): scaffold arcadedb-driver-grpc and its codegen"
```

---

### Task 3: Errors, auth, and the fake-server fixture

**Files:**
- Create: `python/packages/driver-grpc/src/arcadedb_driver_grpc/errors.py`, `auth.py`
- Create: `python/packages/driver-grpc/tests/conftest.py`, `tests/test_auth.py`

**Interfaces:**
- Consumes: `_generated.arcadedb_server_pb2` / `_pb2_grpc` from Task 2.
- Produces:
  - `errors.InsecureChannelError(ValueError)`
  - `auth.Auth` - frozen dataclass with `metadata: tuple[tuple[str, str], ...]` and `sends_plaintext_password: bool`
  - `auth.bearer_auth(token: str) -> Auth`
  - `auth.password_auth(user: str, password: str, database: str | None = None) -> Auth`
  - `auth.sync_interceptors(auth: Auth | None) -> list[grpc.ClientInterceptor]`
  - `auth.async_interceptors(auth: Auth | None) -> list[grpc.aio.ClientInterceptor]`
  - `tests/conftest.py::RecordingServicer` and the `fake_server` fixture, used by Tasks 4-7.

**Design note for the implementer:** `bearer_auth` and `password_auth` return a *value*, not an interceptor. Sync and async gRPC use different, incompatible interceptor base classes, and returning a value lets one pair of public helpers serve both facades instead of four helpers serving two.

- [ ] **Step 1: Write the fake-server fixture**

Create `packages/driver-grpc/tests/conftest.py`:

```python
"""Fixtures for the unit suite: a real in-process gRPC server with a recording servicer.

Deliberately not a mocked stub. gRPC has no `respx` equivalent, and mocking the stub
would skip the two properties most worth asserting - that channel interceptors really
do put `x-arcade-user` on the wire, and that `insert_stream` emits the exact envelope
sequence. A fake servicer records what actually arrived.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent import futures

import grpc
import pytest

from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as pb2_grpc


class RecordingServicer(pb2_grpc.ArcadeDbServiceServicer):
    """Records what each RPC received and answers with whatever the test configured."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.metadata: list[tuple[str, str]] = []
        self.insert_chunks: list[pb2.InsertChunk] = []
        self.command_requests: list[pb2.ExecuteCommandRequest] = []
        self.stream_query_requests: list[pb2.StreamQueryRequest] = []
        self.rollback_requests: list[pb2.RollbackTransactionRequest] = []
        # Configurable responses.
        self.transaction_id = "tx-1"
        self.commit_committed = True
        self.commit_message = ""
        self.stream_batches: list[list[str]] = [["a", "b"], ["c"]]

    def _record(self, name: str, context: grpc.ServicerContext) -> None:
        self.calls.append(name)
        self.metadata = [(k, v) for k, v in context.invocation_metadata()]

    def StreamQuery(
        self, request: pb2.StreamQueryRequest, context: grpc.ServicerContext
    ) -> Iterator[pb2.QueryResult]:
        self._record("StreamQuery", context)
        self.stream_query_requests.append(request)
        for batch in self.stream_batches:
            yield pb2.QueryResult(records=[pb2.GrpcRecord(rid=rid) for rid in batch])

    def ExecuteCommand(
        self, request: pb2.ExecuteCommandRequest, context: grpc.ServicerContext
    ) -> pb2.ExecuteCommandResponse:
        self._record("ExecuteCommand", context)
        self.command_requests.append(request)
        return pb2.ExecuteCommandResponse(success=True)

    def InsertStream(
        self, request_iterator: Iterator[pb2.InsertChunk], context: grpc.ServicerContext
    ) -> pb2.InsertSummary:
        self._record("InsertStream", context)
        received = 0
        for chunk in request_iterator:
            self.insert_chunks.append(chunk)
            received += len(chunk.rows)
        return pb2.InsertSummary(received=received, inserted=received)

    def BeginTransaction(
        self, request: pb2.BeginTransactionRequest, context: grpc.ServicerContext
    ) -> pb2.BeginTransactionResponse:
        self._record("BeginTransaction", context)
        return pb2.BeginTransactionResponse(transaction_id=self.transaction_id)

    def CommitTransaction(
        self, request: pb2.CommitTransactionRequest, context: grpc.ServicerContext
    ) -> pb2.CommitTransactionResponse:
        self._record("CommitTransaction", context)
        return pb2.CommitTransactionResponse(
            success=True, committed=self.commit_committed, message=self.commit_message
        )

    def RollbackTransaction(
        self, request: pb2.RollbackTransactionRequest, context: grpc.ServicerContext
    ) -> pb2.RollbackTransactionResponse:
        self._record("RollbackTransaction", context)
        self.rollback_requests.append(request)
        return pb2.RollbackTransactionResponse(success=True, rolled_back=True)


@pytest.fixture
def fake_server() -> Iterator[tuple[str, RecordingServicer]]:
    """Yields `(target, servicer)` for a server on an ephemeral loopback port."""
    servicer = RecordingServicer()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb2_grpc.add_ArcadeDbServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        server.stop(grace=None)
```

- [ ] **Step 2: Write the failing auth tests**

Create `packages/driver-grpc/tests/test_auth.py`:

```python
from __future__ import annotations

import grpc
import pytest

from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc._generated import arcadedb_server_pb2_grpc as pb2_grpc
from arcadedb_driver_grpc.auth import bearer_auth, password_auth, sync_interceptors

from .conftest import RecordingServicer


def _call(target: str, auth: object) -> None:
    channel = grpc.insecure_channel(target)
    intercepted = grpc.intercept_channel(channel, *sync_interceptors(auth))  # type: ignore[arg-type]
    stub = pb2_grpc.ArcadeDbServiceStub(intercepted)
    stub.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    channel.close()


def test_bearer_auth_sets_the_authorization_header(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    _call(target, bearer_auth("t0ken"))
    assert ("authorization", "Bearer t0ken") in servicer.metadata


def test_password_auth_sets_user_password_and_database(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    _call(target, password_auth("root", "playwithdata", "mydb"))
    assert ("x-arcade-user", "root") in servicer.metadata
    assert ("x-arcade-password", "playwithdata") in servicer.metadata
    assert ("x-arcade-database", "mydb") in servicer.metadata


def test_password_auth_omits_the_database_when_not_given(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    _call(target, password_auth("root", "playwithdata"))
    assert not any(key == "x-arcade-database" for key, _ in servicer.metadata)


def test_only_password_auth_is_marked_as_sending_a_plaintext_password() -> None:
    # This marker is what create_client's insecure guard reads. If it stops being
    # set, the guard silently stops guarding - hence a test on the marker itself.
    assert password_auth("root", "playwithdata").sends_plaintext_password is True
    assert bearer_auth("t0ken").sends_plaintext_password is False


def test_no_auth_produces_no_interceptors() -> None:
    assert sync_interceptors(None) == []


def test_interceptors_do_not_discard_metadata_the_caller_already_set(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The interceptor APPENDS. Replacing client_call_details.metadata wholesale would
    # silently drop per-call metadata, which is a data-loss bug no auth test would catch.
    target, servicer = fake_server
    channel = grpc.insecure_channel(target)
    intercepted = grpc.intercept_channel(channel, *sync_interceptors(bearer_auth("t0ken")))
    stub = pb2_grpc.ArcadeDbServiceStub(intercepted)
    stub.ExecuteCommand(
        pb2.ExecuteCommandRequest(database="db", command="SELECT 1"),
        metadata=(("x-caller", "mine"),),
    )
    channel.close()
    assert ("x-caller", "mine") in servicer.metadata
    assert ("authorization", "Bearer t0ken") in servicer.metadata
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest packages/driver-grpc/tests/test_auth.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'arcadedb_driver_grpc.auth'`.

- [ ] **Step 4: Write `errors.py`**

```python
"""Errors raised by this package itself.

Deliberately tiny. Server-side failures surface as `grpc.RpcError` (sync) and
`grpc.aio.AioRpcError` (async), UNWRAPPED - the same asymmetry `python/CLAUDE.md`
documents for TypeScript's `ConnectError` versus `ArcadeDBError`, and not an
oversight to be tidied later.

There is no gRPC equivalent of `arcadedb-driver`'s `unwrap` because there is no
envelope to unwrap. The HTTP contract answers 200 with a body that may describe a
failure, which is why that package needs `_internal/unwrap.py`. A gRPC status code
is not that shape: a failure is a failure at the transport level.
"""

from __future__ import annotations

__all__ = ["InsecureChannelError"]


class InsecureChannelError(ValueError):
    """Raised when a plaintext password would be sent over an unencrypted channel.

    Named rather than a bare `ValueError` so a caller can catch this specific
    refusal without catching every other argument error `create_client` may raise.
    """
```

- [ ] **Step 5: Write `auth.py`**

```python
"""Authentication helpers for ArcadeDB's gRPC data plane.

`bearer_auth` and `password_auth` return a VALUE, not an interceptor. Sync and async
gRPC use different, incompatible interceptor base classes, so returning metadata plus
a marker lets one pair of public helpers serve both facades.

The interceptors are attached to the CHANNEL rather than passed as per-call
`metadata=`. That is not stylistic: a channel interceptor also authenticates calls
made through `client.raw`, and `raw` is where most of the 14 data-plane RPCs live.
The top-level facade wraps five of them - `StreamQuery`, `InsertStream`, and the
`Begin`/`Commit`/`Rollback` trio `transaction()` drives - leaving the other 9
reachable only through `raw`. Opening a transaction narrows that to 3: the six CRUD
RPCs gain a wrapper on the handle, while `BulkInsert`, `InsertBidirectional` and
`GraphBatchLoad` have none anywhere, ever. Per-call metadata on the wrappers would
leave every one of those calls silently anonymous.

Call credentials (`grpc.metadata_call_credentials`) are deliberately not used: they
require a secure channel, and password auth over an insecure channel is exactly the
configuration the e2e suite runs against a test container.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

import grpc

__all__ = ["Auth", "async_interceptors", "bearer_auth", "password_auth", "sync_interceptors"]


@dataclass(frozen=True)
class Auth:
    """Metadata to attach to every outgoing call, plus whether it carries a password."""

    metadata: tuple[tuple[str, str], ...]
    sends_plaintext_password: bool = False


def bearer_auth(token: str) -> Auth:
    """Authenticates with a bearer token: `authorization: Bearer <token>`."""
    return Auth(metadata=(("authorization", f"Bearer {token}"),))


def password_auth(user: str, password: str, database: str | None = None) -> Auth:
    """Authenticates with a username and password.

    Sets `x-arcade-user`, `x-arcade-password` and, when given, `x-arcade-database`.

    The password travels in plaintext metadata, so `create_client` refuses to pair
    this with an insecure channel unless `insecure=True` is passed explicitly.
    """
    metadata: list[tuple[str, str]] = [("x-arcade-user", user), ("x-arcade-password", password)]
    if database is not None:
        metadata.append(("x-arcade-database", database))
    return Auth(metadata=tuple(metadata), sends_plaintext_password=True)


class _CallDetails(NamedTuple):
    """A concrete `grpc.ClientCallDetails`.

    grpc-python passes an implementation-private namedtuple whose `_replace` is not
    part of the public API, so a portable interceptor builds its own.
    """

    method: str
    timeout: float | None
    metadata: Sequence[tuple[str, str]] | None
    credentials: grpc.CallCredentials | None
    wait_for_ready: bool | None
    compression: Any


def _augment(details: grpc.ClientCallDetails, extra: tuple[tuple[str, str], ...]) -> _CallDetails:
    # APPEND, never replace: the caller may have set per-call metadata of their own,
    # and dropping it here would be a silent data-loss bug.
    merged = list(details.metadata or ()) + list(extra)
    return _CallDetails(
        method=details.method,
        timeout=details.timeout,
        metadata=merged,
        credentials=details.credentials,
        wait_for_ready=getattr(details, "wait_for_ready", None),
        compression=getattr(details, "compression", None),
    )


class _SyncAuthInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
    grpc.StreamUnaryClientInterceptor,
    grpc.StreamStreamClientInterceptor,
):
    """One object implementing all four interceptor protocols.

    All four are needed: the data plane uses unary-unary (ExecuteQuery), unary-stream
    (StreamQuery), stream-unary (InsertStream) and stream-stream (InsertBidirectional).
    Implementing three of the four would leave one call shape unauthenticated.
    """

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    def _intercept(
        self, continuation: Callable[..., Any], details: grpc.ClientCallDetails, payload: Any
    ) -> Any:
        return continuation(_augment(details, self._extra), payload)

    intercept_unary_unary = _intercept
    intercept_unary_stream = _intercept
    intercept_stream_unary = _intercept
    intercept_stream_stream = _intercept


class _AsyncAuthInterceptor(
    grpc.aio.UnaryUnaryClientInterceptor,
    grpc.aio.UnaryStreamClientInterceptor,
    grpc.aio.StreamUnaryClientInterceptor,
    grpc.aio.StreamStreamClientInterceptor,
):
    """The `grpc.aio` twin of `_SyncAuthInterceptor`; its hooks are coroutines."""

    def __init__(self, auth: Auth) -> None:
        self._extra = auth.metadata

    async def _intercept(
        self, continuation: Callable[..., Any], details: grpc.ClientCallDetails, payload: Any
    ) -> Any:
        return await continuation(_augment(details, self._extra), payload)

    intercept_unary_unary = _intercept
    intercept_unary_stream = _intercept
    intercept_stream_unary = _intercept
    intercept_stream_stream = _intercept


def sync_interceptors(auth: Auth | None) -> list[grpc.ClientInterceptor]:
    """Channel interceptors for a sync channel; empty when `auth` is None."""
    return [] if auth is None else [_SyncAuthInterceptor(auth)]


def async_interceptors(auth: Auth | None) -> list[grpc.aio.ClientInterceptor]:
    """Channel interceptors for an async channel; empty when `auth` is None."""
    return [] if auth is None else [_AsyncAuthInterceptor(auth)]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest packages/driver-grpc/tests/test_auth.py -v`
Expected: 6 passed.

If `intercept_stream_stream` raises a signature error, the four aliases have bound the wrong argument name - write the four methods out longhand rather than aliasing.

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
cd .. && git add python/ && git commit -m "feat(python-grpc): auth helpers and the in-process fake server fixture"
```

---

### Task 4: `create_client` and the insecure guard

**Files:**
- Modify: `python/packages/driver-grpc/src/arcadedb_driver_grpc/__init__.py`
- Create: `python/packages/driver-grpc/tests/test_client.py`

**Interfaces:**
- Consumes: `auth.Auth`, `auth.sync_interceptors`, `errors.InsecureChannelError`, `_pb2_grpc.ArcadeDbServiceStub`.
- Produces:
  - `create_client(target: str, *, auth: Auth | None = None, credentials: grpc.ChannelCredentials | None = None, insecure: bool = False) -> ArcadeDBGrpcClient`
  - `ArcadeDBGrpcClient` with `.raw: ArcadeDbServiceStub`, `.close() -> None`, `__enter__`/`__exit__`. Tasks 5-7 add `stream_query`, `insert_stream` and `transaction` methods to this class.

- [ ] **Step 1: Write the failing tests**

Create `packages/driver-grpc/tests/test_client.py`:

```python
from __future__ import annotations

import grpc
import pytest

from arcadedb_driver_grpc import InsecureChannelError, create_client
from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2
from arcadedb_driver_grpc.auth import bearer_auth, password_auth

from .conftest import RecordingServicer


def test_raw_reaches_the_server(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]


def test_raw_is_authenticated_too(fake_server: tuple[str, RecordingServicer]) -> None:
    # The reason auth is a CHANNEL interceptor. Of the 14 data-plane RPCs the facade
    # wraps five, so 9 are reachable only through `raw` outside a transaction and 3
    # (BulkInsert, InsertBidirectional, GraphBatchLoad) even inside one; per-call
    # metadata on the facade would leave every one of them anonymous.
    target, servicer = fake_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
        client.raw.ExecuteCommand(pb2.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert ("authorization", "Bearer t0ken") in servicer.metadata


def test_password_auth_over_an_insecure_channel_is_refused() -> None:
    with pytest.raises(InsecureChannelError):
        create_client("127.0.0.1:50051", auth=password_auth("root", "playwithdata"))


def test_password_auth_over_an_insecure_channel_is_allowed_when_opted_into(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, _ = fake_server
    with create_client(target, auth=password_auth("root", "playwithdata"), insecure=True) as client:
        assert client.raw is not None


def test_bearer_auth_over_an_insecure_channel_is_not_refused(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A bearer token is not a password. The guard is specifically about plaintext
    # passwords, so it must not fire here or callers will pass insecure=True by reflex.
    target, _ = fake_server
    with create_client(target, auth=bearer_auth("t0ken")) as client:
        assert client.raw is not None


def test_password_auth_over_a_secure_channel_is_not_refused() -> None:
    client = create_client(
        "127.0.0.1:50051",
        auth=password_auth("root", "playwithdata"),
        credentials=grpc.ssl_channel_credentials(),
    )
    client.close()


def test_close_is_idempotent(fake_server: tuple[str, RecordingServicer]) -> None:
    target, _ = fake_server
    client = create_client(target)
    client.close()
    client.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/driver-grpc/tests/test_client.py -v`
Expected: FAIL - `ImportError: cannot import name 'create_client'`.

- [ ] **Step 3: Implement in `__init__.py`**

Replace the placeholder `__init__.py` with:

```python
"""Python gRPC client for ArcadeDB's data plane, generated from ArcadeDB's protobuf contract."""

from __future__ import annotations

from types import TracebackType

import grpc

from ._generated import arcadedb_server_pb2 as messages
from ._generated import arcadedb_server_pb2_grpc as _pb2_grpc
from .auth import Auth, bearer_auth, password_auth, sync_interceptors
from .errors import InsecureChannelError

__version__ = "0.1.0"

__all__ = [
    "ArcadeDBGrpcClient",
    "Auth",
    "InsecureChannelError",
    "__version__",
    "bearer_auth",
    "create_client",
    "messages",
    "password_auth",
]


class ArcadeDBGrpcClient:
    """ArcadeDB's gRPC data-plane client.

    `raw` is the generated stub for `com.arcadedb.grpc.ArcadeDbService`; every RPC the
    facade does not wrap is reached through it, already authenticated.

    A `grpc.Channel` must be closed, so this is a context manager. `@arcadedb/driver-grpc`
    has no counterpart because Connect's transport needs no teardown.
    """

    def __init__(self, channel: grpc.Channel) -> None:
        self._channel = channel
        self.raw = _pb2_grpc.ArcadeDbServiceStub(channel)

    def close(self) -> None:
        """Closes the underlying channel. Safe to call more than once."""
        self._channel.close()

    def __enter__(self) -> ArcadeDBGrpcClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def create_client(
    target: str,
    *,
    auth: Auth | None = None,
    credentials: grpc.ChannelCredentials | None = None,
    insecure: bool = False,
) -> ArcadeDBGrpcClient:
    """Creates a gRPC data-plane client.

    `target` is gRPC's native `host:port` form, e.g. `"localhost:50051"` - not a URL.

    Refuses to pair `password_auth` with an insecure channel unless `insecure=True` is
    passed explicitly: sending a password in cleartext metadata is a credential-exposure
    hazard (issue #5048). The check keys on whether channel `credentials` were supplied,
    which is stated outright rather than inferred - the TypeScript client has to defend
    against `new URL("localhost:50051").protocol` evaluating to `"localhost:"` instead
    of `"http:"`, and Python has no such trap.
    """
    if credentials is None and not insecure and auth is not None and auth.sends_plaintext_password:
        raise InsecureChannelError(
            f'create_client: refusing to send a plaintext password over an insecure channel to "{target}". '
            "Pass credentials=grpc.ssl_channel_credentials(), switch to bearer_auth, "
            "or pass insecure=True to opt in explicitly."
        )

    interceptors = sync_interceptors(auth)
    channel = (
        grpc.insecure_channel(target)
        if credentials is None
        else grpc.secure_channel(target, credentials)
    )
    if interceptors:
        channel = grpc.intercept_channel(channel, *interceptors)
    return ArcadeDBGrpcClient(channel)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/driver-grpc/tests/test_client.py -v`
Expected: 7 passed.

Note on `test_close_is_idempotent`: `grpc.intercept_channel` returns a wrapper whose `close()` delegates. If closing twice raises, wrap `close()`'s body in a `try/except ValueError` and add a comment explaining which grpc version required it - do not silence it with a bare `except`.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
cd .. && git add python/ && git commit -m "feat(python-grpc): create_client with the plaintext-password guard"
```

---

### Task 5: `stream_query`

**Files:**
- Create: `python/packages/driver-grpc/src/arcadedb_driver_grpc/stream.py`
- Create: `python/packages/driver-grpc/tests/test_stream.py`
- Modify: `python/packages/driver-grpc/src/arcadedb_driver_grpc/__init__.py`

**Interfaces:**
- Consumes: `ArcadeDBGrpcClient` from Task 4.
- Produces: `stream.stream_query(raw: ArcadeDbServiceStub, request: messages.StreamQueryRequest, *, timeout: float | None = None) -> Iterator[messages.GrpcRecord]`, and `ArcadeDBGrpcClient.stream_query(request, *, timeout=None)` delegating to it. Task 7 reuses `stream_query` for the transaction-bound variant; Task 8 mirrors it in `aio.py`.

- [ ] **Step 1: Write the failing tests**

Create `packages/driver-grpc/tests/test_stream.py`:

```python
from __future__ import annotations

from arcadedb_driver_grpc import create_client, messages

from .conftest import RecordingServicer


def test_flattens_batches_into_individual_records(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.stream_batches = [["#1:0", "#1:1"], ["#1:2"]]
    with create_client(target) as client:
        rids = [r.rid for r in client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"))]
    assert rids == ["#1:0", "#1:1", "#1:2"]


def test_an_empty_stream_yields_nothing_rather_than_raising(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.stream_batches = []
    with create_client(target) as client:
        assert list(client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"))) == []


def test_retrieval_mode_and_batch_size_pass_through_untouched(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The wrapper must pick NO defaults: CURSOR, MATERIALIZE_ALL and PAGED have
    # materially different memory and consistency behaviour that only the caller can judge.
    target, servicer = fake_server
    with create_client(target) as client:
        list(
            client.stream_query(
                messages.StreamQueryRequest(
                    database="db",
                    query="SELECT 1",
                    batch_size=7,
                    retrieval_mode=messages.StreamQueryRequest.RetrievalMode.PAGED,
                )
            )
        )
    sent = servicer.stream_query_requests[0]
    assert sent.batch_size == 7
    assert sent.retrieval_mode == messages.StreamQueryRequest.RetrievalMode.PAGED


def test_a_request_with_no_batch_size_sends_no_batch_size(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        list(client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1")))
    assert servicer.stream_query_requests[0].batch_size == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/driver-grpc/tests/test_stream.py -v`
Expected: FAIL - `AttributeError: 'ArcadeDBGrpcClient' object has no attribute 'stream_query'`.

- [ ] **Step 3: Create `stream.py`**

```python
"""The two streaming wrappers: `stream_query` and `insert_stream`."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub

__all__ = ["stream_query"]


def stream_query(
    raw: ArcadeDbServiceStub,
    request: messages.StreamQueryRequest,
    *,
    timeout: float | None = None,
) -> Iterator[messages.GrpcRecord]:
    """Streams a query's results row by row.

    Wraps the server-streaming `StreamQuery`, flattening the batching the wire protocol
    uses: the server sends `QueryResult` batches, this yields each `GrpcRecord` on its own.

    Thin by design. `retrieval_mode` and `batch_size` pass through to the server exactly
    as given and this wrapper picks no defaults for either, because CURSOR,
    MATERIALIZE_ALL and PAGED have materially different memory and consistency behaviour
    that only the caller can judge.
    """
    for result in raw.StreamQuery(request, timeout=timeout):
        yield from result.records
```

- [ ] **Step 4: Wire it onto the client**

In `__init__.py`, add the import and the method:

```python
from .stream import stream_query as _stream_query
```

and inside `ArcadeDBGrpcClient`:

```python
    def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> Iterator[messages.GrpcRecord]:
        """Streams a query's results row by row. See `stream.stream_query`."""
        return _stream_query(self.raw, request, timeout=timeout)
```

Add `from collections.abc import Iterator` to the imports.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/driver-grpc/tests/test_stream.py -v`
Expected: 4 passed.

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
cd .. && git add python/ && git commit -m "feat(python-grpc): stream_query"
```

---

### Task 6: `insert_stream`

The wrapper that earns its keep. Read section 8 of the spec before starting: the `options.database` mirroring is an empirically established server workaround, not a belt-and-braces flourish, and removing it breaks every stream against a 26.9.1 server.

**Files:**
- Modify: `python/packages/driver-grpc/src/arcadedb_driver_grpc/stream.py`, `__init__.py`
- Modify: `python/packages/driver-grpc/tests/test_stream.py`

**Interfaces:**
- Consumes: Task 5's `stream.py`.
- Produces:
  - `stream.InsertStreamRequest` - dataclass with `database: str`, `chunks: Iterable[Sequence[messages.GrpcRecord]] | AsyncIterable[Sequence[messages.GrpcRecord]]`, `credentials: messages.DatabaseCredentials | None = None`, `options: messages.InsertOptions | None = None`, `transaction: messages.TransactionContext | None = None`

  The `chunks` union is deliberate: **one** request type serves both facades. The sync `insert_stream` rejects an async iterable at runtime with a clear message, and the async one accepts either. Splitting this into two dataclasses would double the type for no gain, since every other field is identical.
  - `stream.insert_stream(raw, request, *, timeout=None) -> messages.InsertSummary`
  - `stream._build_chunk(request, session_id: str, seq: int, rows: Sequence[messages.GrpcRecord], *, last: bool) -> messages.InsertChunk` - **Task 8 imports this**, so keep the name and signature. It is pure message construction with no I/O, which is why both facades share it; only the iteration around it differs.
  - `stream._envelope_chunks(request, session_id: str) -> Iterator[messages.InsertChunk]` - the sync iteration; Task 6's finalisation test imports it directly.
  - `ArcadeDBGrpcClient.insert_stream(request, *, timeout=None)`

- [ ] **Step 1: Write the failing tests**

Append to `packages/driver-grpc/tests/test_stream.py`:

```python
def _records(*rids: str) -> list[messages.GrpcRecord]:
    return [messages.GrpcRecord(rid=rid) for rid in rids]


def test_envelope_bookkeeping_across_several_chunks(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        summary = client.insert_stream(
            InsertStreamRequest(database="db", chunks=[_records("a"), _records("b"), _records("c")])
        )

    chunks = servicer.insert_chunks
    assert len(chunks) == 3
    assert [c.chunk_seq for c in chunks] == [1, 2, 3]
    # One session id, stable for the whole stream, and non-empty.
    assert len({c.session_id for c in chunks}) == 1
    assert chunks[0].session_id != ""
    # `database` on the FIRST chunk only, per the .proto contract.
    assert chunks[0].database == "db"
    assert [c.database for c in chunks[1:]] == ["", ""]
    # `last` on the FINAL chunk only.
    assert [c.last for c in chunks] == [False, False, True]
    assert summary.received == 3


def test_the_first_chunk_mirrors_database_into_options(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # Compatibility with servers predating the fix for ArcadeData/arcadedb#6597. On
    # 26.9.1 and earlier the server builds InsertContext from InsertOptions.database
    # ALONE and never reads InsertChunk.database, despite the .proto marking the latter
    # REQUIRED on the first chunk. Without this mirror every stream fails at the
    # deferred commit with "Invalid database name: name is required".
    target, servicer = fake_server
    with create_client(target) as client:
        client.insert_stream(InsertStreamRequest(database="db", chunks=[_records("a")]))
    assert servicer.insert_chunks[0].options.database == "db"


def test_mirroring_preserves_the_callers_other_options(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    with create_client(target) as client:
        client.insert_stream(
            InsertStreamRequest(
                database="db",
                chunks=[_records("a")],
                options=messages.InsertOptions(target_class="Person", server_batch_size=32),
            )
        )
    sent = servicer.insert_chunks[0].options
    assert sent.database == "db"
    assert sent.target_class == "Person"
    assert sent.server_batch_size == 32


def test_an_empty_stream_sends_one_empty_final_chunk_rather_than_raising(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A filter that matched nothing is a legitimate outcome, not an error - the same
    # principle both READMEs argue for `truncated`. M1b verified against a real server
    # that such a chunk is accepted cleanly and answers an all-zero InsertSummary.
    target, servicer = fake_server
    with create_client(target) as client:
        summary = client.insert_stream(InsertStreamRequest(database="db", chunks=[]))

    assert len(servicer.insert_chunks) == 1
    only = servicer.insert_chunks[0]
    assert list(only.rows) == []
    assert only.last is True
    assert only.chunk_seq == 1
    assert only.database == "db"
    assert only.options.database == "db"
    assert summary.received == 0


def test_the_callers_iterator_is_finalised_when_the_stream_ends() -> None:
    # The chunk iterator is pulled MANUALLY, because knowing which chunk is last needs
    # one-element lookahead. Manual pulling means finalisation is not automatic, so the
    # caller's own `finally` - closing a file handle, a cursor - must still run.
    closed = False

    def chunks() -> Iterator[list[messages.GrpcRecord]]:
        nonlocal closed
        try:
            yield _records("a")
            yield _records("b")
        finally:
            closed = True

    from arcadedb_driver_grpc.stream import _envelope_chunks

    list(_envelope_chunks(InsertStreamRequest(database="db", chunks=chunks()), "session-1"))
    assert closed is True
```

Add to that file's imports:

```python
from collections.abc import Iterator

from arcadedb_driver_grpc import InsertStreamRequest
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/driver-grpc/tests/test_stream.py -v`
Expected: FAIL - `ImportError: cannot import name 'InsertStreamRequest'`.

- [ ] **Step 3: Implement in `stream.py`**

Add these imports at the top:

```python
import uuid
from collections.abc import AsyncIterable, Iterable, Iterator, Sequence
from dataclasses import dataclass
```

and make the sync path refuse an async iterable rather than failing obscurely inside grpc, at the top of `_envelope_chunks`:

```python
    if not isinstance(request.chunks, Iterable):
        raise TypeError(
            "insert_stream: `chunks` is an async iterable, which the sync facade cannot consume. "
            "Use arcadedb_driver_grpc.aio.create_client, or pass a synchronous iterable."
        )
```

and extend `__all__` to `["InsertStreamRequest", "insert_stream", "stream_query"]`. Then append:

```python
@dataclass
class InsertStreamRequest:
    """A client-streaming insert.

    `chunks` is the sequence of row batches to send - each element becomes exactly one
    wire `InsertChunk`. This wrapper owns the envelope bookkeeping around those batches
    (`session_id`, `chunk_seq`, first-chunk-only `database`, final-chunk `last`); it does
    not decide how rows are batched, which is the caller's call.
    """

    database: str
    chunks: Iterable[Sequence[messages.GrpcRecord]] | AsyncIterable[Sequence[messages.GrpcRecord]]
    credentials: messages.DatabaseCredentials | None = None
    options: messages.InsertOptions | None = None
    transaction: messages.TransactionContext | None = None


def _first_chunk_options(request: InsertStreamRequest) -> messages.InsertOptions:
    """The caller's options with `database` forced onto them.

    Empirically established during M1b against a real server: on 26.9.1 and every
    earlier release the server builds its `InsertContext` from `InsertOptions.database`
    ALONE and never reads `InsertChunk.database` at all, despite the .proto documenting
    the latter as REQUIRED on the first chunk. Without this mirror every stream against
    such a server fails at the deferred commit with "Invalid database name: name is
    required", even though `database` was sent exactly as the contract specifies.

    A server carrying the fix for ArcadeData/arcadedb#6597 prefers a non-empty chunk
    `database` and falls back to this one, so setting both to the same value is correct
    on either side of that fix.
    """
    options = messages.InsertOptions()
    if request.options is not None:
        options.CopyFrom(request.options)
    options.database = request.database
    return options


def _build_chunk(
    request: InsertStreamRequest,
    session_id: str,
    seq: int,
    rows: Sequence[messages.GrpcRecord],
    *,
    last: bool,
) -> messages.InsertChunk:
    chunk = messages.InsertChunk(session_id=session_id, chunk_seq=seq, rows=rows, last=last)
    if request.credentials is not None:
        chunk.credentials.CopyFrom(request.credentials)
    if request.transaction is not None:
        chunk.transaction.CopyFrom(request.transaction)
    if seq == 1:
        # `database` on the first chunk only, per the .proto contract, and mirrored
        # into options there too - see `_first_chunk_options`.
        chunk.database = request.database
        chunk.options.CopyFrom(_first_chunk_options(request))
    elif request.options is not None:
        chunk.options.CopyFrom(request.options)
    return chunk


def _envelope_chunks(request: InsertStreamRequest, session_id: str) -> Iterator[messages.InsertChunk]:
    """Turns `request.chunks` into wire `InsertChunk`s, adding the envelope bookkeeping."""
    iterator = iter(request.chunks)

    # The iterator is pulled MANUALLY rather than with a plain `for`, because knowing
    # which chunk is last needs one-element lookahead. Manual pulling means finalisation
    # is not automatic: if this generator is abandoned early - the RPC aborts mid-stream,
    # or the caller stops consuming - nothing would otherwise close the caller's own
    # iterator, and any `finally` they wrote around it (closing a file handle, a database
    # cursor) would never run. The try/finally makes that cleanup happen on every exit
    # path, not only on normal completion.
    try:
        current = next(iterator, None)
        if current is None:
            # An empty stream is a legitimate outcome, not an error: a filter that matched
            # nothing produces one. Send a single empty final chunk and let the server
            # answer with whatever summary it likes, rather than inventing a result or
            # raising. Verified against a real server during M1b.
            yield _build_chunk(request, session_id, 1, [], last=True)
            return

        seq = 1
        while True:
            nxt = next(iterator, None)
            yield _build_chunk(request, session_id, seq, current, last=nxt is None)
            if nxt is None:
                return
            current = nxt
            seq += 1
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()


def insert_stream(
    raw: ArcadeDbServiceStub,
    request: InsertStreamRequest,
    *,
    timeout: float | None = None,
) -> messages.InsertSummary:
    """Streams rows to the server in chunks and returns the server's single `InsertSummary`.

    Handles the `session_id` / `chunk_seq` / `database` / `last` envelope bookkeeping a
    caller would otherwise hand-roll:

    - one `session_id` (a fresh UUID), stable for the whole stream
    - `chunk_seq` starting at 1 and incrementing by 1
    - `database` on the first chunk only, per the .proto contract, mirrored into
      `options.database` there too for compatibility with servers predating #6597
    - `last=True` on the final chunk only

    An empty `request.chunks` sends a single chunk with zero rows and `last=True` rather
    than raising.

    NOT available on a `TransactionHandle`: ArcadeData/arcadedb#6607 has the server
    ignoring `TransactionContext` here, so offering it there would imply a transactional
    guarantee the server does not honour.
    """
    return raw.InsertStream(_envelope_chunks(request, str(uuid.uuid4())), timeout=timeout)
```

- [ ] **Step 4: Wire it onto the client**

In `__init__.py`, extend the stream import and add the method and the export:

```python
from .stream import InsertStreamRequest
from .stream import insert_stream as _insert_stream
```

```python
    def insert_stream(
        self, request: InsertStreamRequest, *, timeout: float | None = None
    ) -> messages.InsertSummary:
        """Streams rows to the server in chunks. See `stream.insert_stream`."""
        return _insert_stream(self.raw, request, timeout=timeout)
```

Add `"InsertStreamRequest"` to `__all__`, keeping it sorted.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/driver-grpc/tests/test_stream.py -v`
Expected: 9 passed.

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
cd .. && git add python/ && git commit -m "feat(python-grpc): insert_stream with its envelope bookkeeping"
```

---

### Task 7: `transaction`

**Files:**
- Create: `python/packages/driver-grpc/src/arcadedb_driver_grpc/transaction.py`
- Create: `python/packages/driver-grpc/tests/test_transaction.py`
- Modify: `python/packages/driver-grpc/src/arcadedb_driver_grpc/__init__.py`

**Interfaces:**
- Consumes: `stream.stream_query`, `ArcadeDBGrpcClient`.
- Produces:
  - `transaction.TransactionHandle` with `execute_query`, `execute_command`, `create_record`, `update_record`, `delete_record`, `lookup_by_rid`, `stream_query`
  - `transaction.Transaction` - a context manager whose `__enter__` returns a `TransactionHandle`
  - `ArcadeDBGrpcClient.transaction(database: str) -> Transaction`

- [ ] **Step 1: Write the failing tests**

Create `packages/driver-grpc/tests/test_transaction.py`:

```python
from __future__ import annotations

import pytest

from arcadedb_driver_grpc import create_client, messages

from .conftest import RecordingServicer


def test_commits_on_a_clean_exit(fake_server: tuple[str, RecordingServicer]) -> None:
    target, servicer = fake_server
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"))
    assert servicer.calls == ["BeginTransaction", "ExecuteCommand", "CommitTransaction"]


def test_every_call_through_the_handle_carries_the_transaction(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"))
    sent = servicer.command_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.transaction.database == "db"
    assert sent.database == "db"


def test_the_handle_overrides_a_transaction_the_caller_supplied(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # The override IS the mechanism. A caller cannot forget, drop or mismatch the
    # transaction id the way the 2026-07 gRPC audit found three times (#5040-#5042).
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(
                database="somewhere-else",
                command="INSERT INTO P SET n = 1",
                transaction=messages.TransactionContext(transaction_id="tx-forged"),
            )
        )
    sent = servicer.command_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


def test_rolls_back_and_reraises_when_the_body_raises(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught:  # noqa: PT012
        with create_client(target) as client, client.transaction("db"):
            raise sentinel
    assert caught.value is sentinel
    assert "RollbackTransaction" in servicer.calls
    assert "CommitTransaction" not in servicer.calls


def test_refuses_to_run_the_body_without_a_real_transaction_id(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # Running a caller's writes outside a real transaction while implying otherwise is
    # the worst outcome available here, so a blank id refuses BEFORE the body runs.
    target, servicer = fake_server
    servicer.transaction_id = "   "
    ran = False
    with pytest.raises(RuntimeError, match="did not return a transaction id"):  # noqa: PT012
        with create_client(target) as client, client.transaction("db"):
            ran = True
    assert ran is False


def test_raises_when_the_server_reports_the_commit_did_not_take_effect(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # A server that reaped the transaction answers success=true, committed=false with no
    # error status. Reporting success there would silently lose the caller's writes.
    target, servicer = fake_server
    servicer.commit_committed = False
    servicer.commit_message = "transaction was reaped"
    with pytest.raises(RuntimeError, match="did not take effect"):  # noqa: PT012
        with create_client(target) as client, client.transaction("db"):
            pass


def test_stream_query_through_the_handle_is_bound_to_the_transaction(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = fake_server
    servicer.transaction_id = "tx-42"
    with create_client(target) as client, client.transaction("db") as tx:
        list(tx.stream_query(messages.StreamQueryRequest(query="SELECT 1")))
    sent = servicer.stream_query_requests[0]
    assert sent.transaction.transaction_id == "tx-42"
    assert sent.database == "db"


def test_insert_stream_is_not_offered_on_the_handle(
    fake_server: tuple[str, RecordingServicer],
) -> None:
    # ArcadeData/arcadedb#6607: the server ignores TransactionContext for InsertStream
    # and BulkInsert. Offering them here would imply a guarantee it does not honour.
    # Delete this test when #6607 lands and the methods are added.
    target, _ = fake_server
    with create_client(target) as client, client.transaction("db") as tx:
        assert not hasattr(tx, "insert_stream")
        assert not hasattr(tx, "bulk_insert")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest packages/driver-grpc/tests/test_transaction.py -v`
Expected: FAIL - `AttributeError: 'ArcadeDBGrpcClient' object has no attribute 'transaction'`.

- [ ] **Step 3: Create `transaction.py`**

```python
"""The explicit-transaction wrapper.

`BeginTransaction` hands back a `transaction_id` that must be threaded into the
`TransactionContext` of every subsequent request and ended on both the success and the
failure path. That is the footgun the 2026-07 gRPC audit filed three times - transaction
hijack, silent data loss and leaked transactions, #5040 through #5042 - and this module
exists so a caller cannot reproduce them by ergonomics.

Spelled as a CONTEXT MANAGER rather than TypeScript's `transaction(database, fn)`
callback, because `arcadedb-driver` already spells it `with db.transaction() as tx:` and
a caller moving between the two Python drivers should not have to relearn the shape.

`TransactionContext` also carries inline `begin` / `commit` / `rollback` flags, letting a
single request open and commit a transaction on its own. This wrapper covers only the
EXPLICIT model; the inline flags stay reachable by setting the field directly. Wrapping
both would offer two ways to do one thing with different failure modes, and the explicit
one is the one that needs the safety.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import TracebackType
from typing import TypeVar

from ._generated import arcadedb_server_pb2 as messages
from ._generated.arcadedb_server_pb2_grpc import ArcadeDbServiceStub
from .stream import stream_query as _stream_query

__all__ = ["Transaction", "TransactionHandle"]

_Request = TypeVar(
    "_Request",
    messages.ExecuteQueryRequest,
    messages.ExecuteCommandRequest,
    messages.CreateRecordRequest,
    messages.UpdateRecordRequest,
    messages.DeleteRecordRequest,
    messages.LookupByRidRequest,
    messages.StreamQueryRequest,
)


class TransactionHandle:
    """Every call made through this object carries the bound transaction's id.

    Calls made through the outer client do NOT take part in the transaction - the same
    distinction `arcadedb-driver`'s `Transaction` documents for its second
    `ArcadeDBDatabase`.
    """

    def __init__(self, raw: ArcadeDbServiceStub, database: str, transaction_id: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = transaction_id

    def _bind(self, request: _Request) -> _Request:
        """Forces `database` and `transaction` onto `request`, overriding the caller.

        The override is the mechanism, not a detail: it is what makes #5040-#5042
        unrepeatable. A request that arrived naming another database, or carrying another
        transaction id, leaves here naming this one.
        """
        request.database = self._database
        request.transaction.CopyFrom(
            messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)
        )
        return request

    def execute_query(self, request: messages.ExecuteQueryRequest) -> messages.ExecuteQueryResponse:
        return self._raw.ExecuteQuery(self._bind(request))

    def execute_command(self, request: messages.ExecuteCommandRequest) -> messages.ExecuteCommandResponse:
        return self._raw.ExecuteCommand(self._bind(request))

    def create_record(self, request: messages.CreateRecordRequest) -> messages.CreateRecordResponse:
        return self._raw.CreateRecord(self._bind(request))

    def update_record(self, request: messages.UpdateRecordRequest) -> messages.UpdateRecordResponse:
        return self._raw.UpdateRecord(self._bind(request))

    def delete_record(self, request: messages.DeleteRecordRequest) -> messages.DeleteRecordResponse:
        return self._raw.DeleteRecord(self._bind(request))

    def lookup_by_rid(self, request: messages.LookupByRidRequest) -> messages.LookupByRidResponse:
        return self._raw.LookupByRid(self._bind(request))

    def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> Iterator[messages.GrpcRecord]:
        return _stream_query(self._raw, self._bind(request), timeout=timeout)


class Transaction:
    """A server-side transaction, begun on `__enter__` and ended on `__exit__`."""

    def __init__(self, raw: ArcadeDbServiceStub, database: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = ""

    def __enter__(self) -> TransactionHandle:
        begun = self._raw.BeginTransaction(messages.BeginTransactionRequest(database=self._database))
        if not begun.transaction_id.strip():
            raise RuntimeError(
                f'transaction: BeginTransaction did not return a transaction id for database "{self._database}" - '
                "refusing to run the body outside a real transaction."
            )
        self._transaction_id = begun.transaction_id
        return TransactionHandle(self._raw, self._database, self._transaction_id)

    def _context(self) -> messages.TransactionContext:
        return messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)

    def _rollback(self) -> None:
        self._raw.RollbackTransaction(messages.RollbackTransactionRequest(transaction=self._context()))

    def _safe_rollback(self) -> None:
        """Rolls back, swallowing its own failure.

        Used on the commit-failure path only: the commit error is what the caller needs
        to see, and without this attempt the server holds the transaction open until it
        is reaped.
        """
        try:
            self._rollback()
        except Exception:  # noqa: BLE001 - see the docstring; the commit error wins
            pass

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is not None:
            # Roll back, then let the original exception propagate. A rollback failure
            # attaches as __cause__ rather than replacing what the caller actually hit.
            try:
                self._rollback()
            except Exception as rollback_error:  # noqa: BLE001
                if exc.__cause__ is None:
                    exc.__cause__ = rollback_error
            return

        try:
            committed = self._raw.CommitTransaction(
                messages.CommitTransactionRequest(transaction=self._context())
            )
        except Exception:
            self._safe_rollback()
            raise

        if not committed.committed:
            # success=true, committed=false with no error status is what a server answers
            # for a transaction it already reaped. Reporting success would silently lose
            # the caller's writes.
            raise RuntimeError(
                f'transaction: commit for database "{self._database}" '
                f"(transaction_id={self._transaction_id}) did not take effect: "
                f"{committed.message or 'no message from server'}"
            )
```

- [ ] **Step 4: Wire it onto the client**

In `__init__.py`:

```python
from .transaction import Transaction, TransactionHandle
```

```python
    def transaction(self, database: str) -> Transaction:
        """Runs a server-side transaction: `with client.transaction("db") as tx:`."""
        return Transaction(self.raw, database)
```

Add `"Transaction"` and `"TransactionHandle"` to `__all__`, keeping it sorted.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/driver-grpc/tests/test_transaction.py -v`
Expected: 8 passed.

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
cd .. && git add python/ && git commit -m "feat(python-grpc): the transaction context manager"
```

---

### Task 8: The async facade

**Files:**
- Create: `python/packages/driver-grpc/src/arcadedb_driver_grpc/aio.py`
- Create: `python/packages/driver-grpc/tests/test_aio.py`
- Modify: `python/packages/driver-grpc/tests/conftest.py`, `src/arcadedb_driver_grpc/__init__.py`

**Interfaces:**
- Consumes: `auth.async_interceptors`, `errors.InsecureChannelError`, `stream.InsertStreamRequest`.
- Produces: `aio.create_client(...) -> AsyncArcadeDBGrpcClient`, `aio.AsyncArcadeDBGrpcClient`, `aio.AsyncTransaction`, `aio.AsyncTransactionHandle`, all re-exported from the package root.

**Two runtime facts the implementer will hit:**
1. `grpc.aio.insecure_channel(target, interceptors=[...])` takes interceptors as a keyword argument. There is no `grpc.aio` equivalent of `grpc.intercept_channel`.
2. mypy-protobuf models the async stub as a **separate class** (`ArcadeDbServiceAsyncStub`), but grpc constructs the **same** class for both channel kinds. So the constructor call is `ArcadeDbServiceStub(channel)` and the result is `cast` to the async type. That cast is load-bearing typing, not a workaround to remove.

- [ ] **Step 1: Add the async fake-server fixture**

Append to `packages/driver-grpc/tests/conftest.py`:

```python
@pytest.fixture
async def async_fake_server() -> AsyncIterator[tuple[str, RecordingServicer]]:
    """The `grpc.aio` twin of `fake_server`.

    The servicer's methods are sync `def`s, which grpc.aio accepts: it runs them
    directly and treats a returned generator as the response stream. One servicer
    therefore serves both suites.
    """
    servicer = RecordingServicer()
    server = grpc.aio.server()
    pb2_grpc.add_ArcadeDbServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        yield f"127.0.0.1:{port}", servicer
    finally:
        await server.stop(grace=None)
```

Add `AsyncIterator` to the `collections.abc` import.

If grpc.aio rejects the sync servicer methods, make `RecordingServicer` methods `async def` and adapt the sync fixture with a thin sync-wrapping servicer subclass instead — do **not** duplicate the recording logic.

- [ ] **Step 2: Write the failing async tests**

Create `packages/driver-grpc/tests/test_aio.py`:

```python
from __future__ import annotations

import pytest

from arcadedb_driver_grpc import InsecureChannelError, InsertStreamRequest, messages
from arcadedb_driver_grpc.aio import create_client
from arcadedb_driver_grpc.auth import bearer_auth, password_auth

from .conftest import RecordingServicer

pytestmark = pytest.mark.asyncio


async def test_raw_reaches_the_server_and_is_authenticated(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    async with create_client(target, auth=bearer_auth("t0ken")) as client:
        await client.raw.ExecuteCommand(messages.ExecuteCommandRequest(database="db", command="SELECT 1"))
    assert servicer.calls == ["ExecuteCommand"]
    assert ("authorization", "Bearer t0ken") in servicer.metadata


async def test_password_auth_over_an_insecure_channel_is_refused() -> None:
    with pytest.raises(InsecureChannelError):
        create_client("127.0.0.1:50051", auth=password_auth("root", "playwithdata"))


async def test_stream_query_flattens_batches(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.stream_batches = [["#1:0", "#1:1"], ["#1:2"]]
    async with create_client(target) as client:
        rids = [
            r.rid
            async for r in client.stream_query(messages.StreamQueryRequest(database="db", query="SELECT 1"))
        ]
    assert rids == ["#1:0", "#1:1", "#1:2"]


async def test_insert_stream_envelope_bookkeeping(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server

    async def chunks() -> object:
        yield [messages.GrpcRecord(rid="a")]
        yield [messages.GrpcRecord(rid="b")]

    async with create_client(target) as client:
        await client.insert_stream(InsertStreamRequest(database="db", chunks=chunks()))

    sent = servicer.insert_chunks
    assert [c.chunk_seq for c in sent] == [1, 2]
    assert [c.last for c in sent] == [False, True]
    assert sent[0].database == "db"
    assert sent[0].options.database == "db"
    assert sent[1].database == ""


async def test_an_empty_async_stream_sends_one_empty_final_chunk(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server

    async def chunks() -> object:
        return
        yield  # pragma: no cover - makes this an async generator

    async with create_client(target) as client:
        await client.insert_stream(InsertStreamRequest(database="db", chunks=chunks()))

    assert len(servicer.insert_chunks) == 1
    assert servicer.insert_chunks[0].last is True
    assert list(servicer.insert_chunks[0].rows) == []


async def test_transaction_commits_and_binds(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = "tx-42"
    async with create_client(target) as client:
        async with client.transaction("db") as tx:
            await tx.execute_command(messages.ExecuteCommandRequest(command="INSERT INTO P SET n = 1"))
    assert servicer.calls == ["BeginTransaction", "ExecuteCommand", "CommitTransaction"]
    assert servicer.command_requests[0].transaction.transaction_id == "tx-42"


async def test_transaction_rolls_back_and_reraises(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught:  # noqa: PT012
        async with create_client(target) as client:
            async with client.transaction("db"):
                raise sentinel
    assert caught.value is sentinel
    assert "RollbackTransaction" in servicer.calls
    assert "CommitTransaction" not in servicer.calls


async def test_transaction_raises_when_the_commit_did_not_take_effect(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.commit_committed = False
    with pytest.raises(RuntimeError, match="did not take effect"):  # noqa: PT012
        async with create_client(target) as client:
            async with client.transaction("db"):
                pass


async def test_refuses_to_run_the_body_without_a_real_transaction_id(
    async_fake_server: tuple[str, RecordingServicer],
) -> None:
    target, servicer = async_fake_server
    servicer.transaction_id = ""
    ran = False
    with pytest.raises(RuntimeError, match="did not return a transaction id"):  # noqa: PT012
        async with create_client(target) as client:
            async with client.transaction("db"):
                ran = True
    assert ran is False
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest packages/driver-grpc/tests/test_aio.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'arcadedb_driver_grpc.aio'`.

- [ ] **Step 4: Write `aio.py`**

Mirror the sync facade exactly. The whole module is the async twin of `__init__.py`, `stream.py` and `transaction.py`; keep the docstrings that explain *why* (the `options.database` mirroring, the empty-stream decision, the commit-flag check, the binding override) rather than pointing at the sync file — a reader of `aio.py` should not have to open another file to learn the contract.

```python
"""The async facade: the same surface as the package root, over `grpc.aio`.

Two facades over one generated layer, as `python/CLAUDE.md` documents for
`arcadedb-driver`. Not `unasync` or any other single-source generation.

The reasoning behind each wrapper is repeated here rather than cross-referenced,
deliberately: a reader of this module should not have to open `stream.py` and
`transaction.py` to learn what the contract is.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterable, Sequence
from types import TracebackType
from typing import TypeVar, cast

import grpc

from ._generated import arcadedb_server_pb2 as messages
from ._generated import arcadedb_server_pb2_grpc as _pb2_grpc
from .auth import Auth, async_interceptors
from .errors import InsecureChannelError
from .stream import InsertStreamRequest, _build_chunk

__all__ = [
    "AsyncArcadeDBGrpcClient",
    "AsyncTransaction",
    "AsyncTransactionHandle",
    "create_client",
]

_Request = TypeVar(
    "_Request",
    messages.ExecuteQueryRequest,
    messages.ExecuteCommandRequest,
    messages.CreateRecordRequest,
    messages.UpdateRecordRequest,
    messages.DeleteRecordRequest,
    messages.LookupByRidRequest,
    messages.StreamQueryRequest,
)


async def _aiter_chunks(
    chunks: Iterable[Sequence[messages.GrpcRecord]] | AsyncIterator[Sequence[messages.GrpcRecord]],
) -> AsyncIterator[Sequence[messages.GrpcRecord]]:
    """Normalises a sync or async iterable of row batches into an async iterator.

    A caller who already has a list should not have to wrap it in an async generator
    just to reach the async facade.
    """
    if isinstance(chunks, Iterable):
        for chunk in chunks:
            yield chunk
        return
    async for chunk in chunks:
        yield chunk


async def _envelope_chunks(
    request: InsertStreamRequest, session_id: str
) -> AsyncIterator[messages.InsertChunk]:
    """The async twin of `stream._envelope_chunks`; same envelope contract.

    Adds one `session_id` stable for the whole stream, `chunk_seq` from 1, `database`
    on the first chunk only (mirrored into `options.database` there too, for servers
    predating ArcadeData/arcadedb#6597), and `last=True` on the final chunk only.

    Knowing which chunk is last needs one-element lookahead, so the source is pulled
    manually. Manual pulling means finalisation is not automatic, so the try/finally
    closes the caller's own generator on every exit path - not only on normal
    completion - and any `finally` they wrote around it still runs.
    """
    source = _aiter_chunks(request.chunks)
    try:
        current = await anext(source, None)
        if current is None:
            # An empty stream is a legitimate outcome, not an error: a filter that
            # matched nothing produces one. Send a single empty final chunk and hand
            # back whatever summary the server gives, rather than raising or inventing
            # a result. Verified against a real server during M1b.
            yield _build_chunk(request, session_id, 1, [], last=True)
            return

        seq = 1
        while True:
            nxt = await anext(source, None)
            yield _build_chunk(request, session_id, seq, current, last=nxt is None)
            if nxt is None:
                return
            current = nxt
            seq += 1
    finally:
        await source.aclose()


class AsyncTransactionHandle:
    """Every call made through this object carries the bound transaction's id.

    Calls made through the outer client do NOT take part in the transaction.
    """

    def __init__(
        self, raw: _pb2_grpc.ArcadeDbServiceAsyncStub, database: str, transaction_id: str
    ) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = transaction_id

    def _bind(self, request: _Request) -> _Request:
        """Forces `database` and `transaction` onto `request`, overriding the caller.

        The override is the mechanism, not a detail: it is what makes the 2026-07
        audit's #5040-#5042 unrepeatable.
        """
        request.database = self._database
        request.transaction.CopyFrom(
            messages.TransactionContext(transaction_id=self._transaction_id, database=self._database)
        )
        return request

    async def execute_query(
        self, request: messages.ExecuteQueryRequest
    ) -> messages.ExecuteQueryResponse:
        return await self._raw.ExecuteQuery(self._bind(request))

    async def execute_command(
        self, request: messages.ExecuteCommandRequest
    ) -> messages.ExecuteCommandResponse:
        return await self._raw.ExecuteCommand(self._bind(request))

    async def create_record(
        self, request: messages.CreateRecordRequest
    ) -> messages.CreateRecordResponse:
        return await self._raw.CreateRecord(self._bind(request))

    async def update_record(
        self, request: messages.UpdateRecordRequest
    ) -> messages.UpdateRecordResponse:
        return await self._raw.UpdateRecord(self._bind(request))

    async def delete_record(
        self, request: messages.DeleteRecordRequest
    ) -> messages.DeleteRecordResponse:
        return await self._raw.DeleteRecord(self._bind(request))

    async def lookup_by_rid(
        self, request: messages.LookupByRidRequest
    ) -> messages.LookupByRidResponse:
        return await self._raw.LookupByRid(self._bind(request))

    async def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.GrpcRecord]:
        async for result in self._raw.StreamQuery(self._bind(request), timeout=timeout):
            for record in result.records:
                yield record


class AsyncTransaction:
    """A server-side transaction, begun on `__aenter__` and ended on `__aexit__`."""

    def __init__(self, raw: _pb2_grpc.ArcadeDbServiceAsyncStub, database: str) -> None:
        self._raw = raw
        self._database = database
        self._transaction_id = ""

    async def __aenter__(self) -> AsyncTransactionHandle:
        begun = await self._raw.BeginTransaction(
            messages.BeginTransactionRequest(database=self._database)
        )
        if not begun.transaction_id.strip():
            raise RuntimeError(
                f'transaction: BeginTransaction did not return a transaction id for database "{self._database}" - '
                "refusing to run the body outside a real transaction."
            )
        self._transaction_id = begun.transaction_id
        return AsyncTransactionHandle(self._raw, self._database, self._transaction_id)

    def _context(self) -> messages.TransactionContext:
        return messages.TransactionContext(
            transaction_id=self._transaction_id, database=self._database
        )

    async def _rollback(self) -> None:
        await self._raw.RollbackTransaction(
            messages.RollbackTransactionRequest(transaction=self._context())
        )

    async def _safe_rollback(self) -> None:
        """Rolls back, swallowing its own failure.

        Commit-failure path only: the commit error is what the caller needs to see, and
        without this attempt the server holds the transaction open until it is reaped.
        """
        try:
            await self._rollback()
        except Exception:  # noqa: BLE001 - see the docstring; the commit error wins
            pass

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is not None:
            # Roll back, then let the original exception propagate. A rollback failure
            # attaches as __cause__ rather than replacing what the caller actually hit.
            try:
                await self._rollback()
            except Exception as rollback_error:  # noqa: BLE001
                if exc.__cause__ is None:
                    exc.__cause__ = rollback_error
            return

        try:
            committed = await self._raw.CommitTransaction(
                messages.CommitTransactionRequest(transaction=self._context())
            )
        except Exception:
            await self._safe_rollback()
            raise

        if not committed.committed:
            # success=true, committed=false with no error status is what a server answers
            # for a transaction it already reaped. Reporting success would silently lose
            # the caller's writes.
            raise RuntimeError(
                f'transaction: commit for database "{self._database}" '
                f"(transaction_id={self._transaction_id}) did not take effect: "
                f"{committed.message or 'no message from server'}"
            )


class AsyncArcadeDBGrpcClient:
    """ArcadeDB's async gRPC data-plane client.

    `raw` is the generated stub; every RPC the facade does not wrap is reached through
    it, already authenticated.
    """

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._channel = channel
        # mypy-protobuf models the async stub as its own class, but grpc constructs the
        # SAME class for both channel kinds. The cast is how the async types are reached:
        # load-bearing typing, not a workaround to be removed.
        self.raw = cast(_pb2_grpc.ArcadeDbServiceAsyncStub, _pb2_grpc.ArcadeDbServiceStub(channel))

    async def close(self) -> None:
        """Closes the underlying channel."""
        await self._channel.close(grace=None)

    async def __aenter__(self) -> AsyncArcadeDBGrpcClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def stream_query(
        self, request: messages.StreamQueryRequest, *, timeout: float | None = None
    ) -> AsyncIterator[messages.GrpcRecord]:
        """Streams a query's results row by row, flattening the wire batching.

        `retrieval_mode` and `batch_size` pass through unchanged; this wrapper picks no
        default for either, because the three retrieval modes have materially different
        memory and consistency behaviour that only the caller can judge.
        """
        async for result in self.raw.StreamQuery(request, timeout=timeout):
            for record in result.records:
                yield record

    async def insert_stream(
        self, request: InsertStreamRequest, *, timeout: float | None = None
    ) -> messages.InsertSummary:
        """Streams rows to the server in chunks, handling the envelope bookkeeping.

        NOT available on `AsyncTransactionHandle`: ArcadeData/arcadedb#6607 has the
        server ignoring `TransactionContext` here, so offering it there would imply a
        transactional guarantee the server does not honour.
        """
        return await self.raw.InsertStream(
            _envelope_chunks(request, str(uuid.uuid4())), timeout=timeout
        )

    def transaction(self, database: str) -> AsyncTransaction:
        """Runs a server-side transaction: `async with client.transaction("db") as tx:`."""
        return AsyncTransaction(self.raw, database)


def create_client(
    target: str,
    *,
    auth: Auth | None = None,
    credentials: grpc.ChannelCredentials | None = None,
    insecure: bool = False,
) -> AsyncArcadeDBGrpcClient:
    """The async twin of the package root's `create_client`, with the same guard.

    The guard is written out here rather than factored into a shared helper: one
    duplicated `if` is cheaper to read than an indirection, and this is the check people
    audit.
    """
    if credentials is None and not insecure and auth is not None and auth.sends_plaintext_password:
        raise InsecureChannelError(
            f'create_client: refusing to send a plaintext password over an insecure channel to "{target}". '
            "Pass credentials=grpc.ssl_channel_credentials(), switch to bearer_auth, "
            "or pass insecure=True to opt in explicitly."
        )

    interceptors = async_interceptors(auth)
    channel = (
        grpc.aio.insecure_channel(target, interceptors=interceptors)
        if credentials is None
        else grpc.aio.secure_channel(target, credentials, interceptors=interceptors)
    )
    return AsyncArcadeDBGrpcClient(channel)
```

Three notes that will save time:

- `_build_chunk` is imported from `stream.py` and reused. It is pure message construction with no I/O, so both facades share it; only the *iteration* differs.
- `anext(source, None)` needs Python 3.10+, which is the declared floor. If mypy objects to the two-argument form, use `source.__anext__()` inside `try/except StopAsyncIteration`.
- `grpc.aio.insecure_channel` takes `interceptors` as a keyword argument. There is no `grpc.aio` equivalent of `grpc.intercept_channel`, so do not look for one.

- [ ] **Step 5: Re-export from the package root**

In `__init__.py`:

```python
from .aio import AsyncArcadeDBGrpcClient, AsyncTransaction, AsyncTransactionHandle
```

and add those three names to `__all__`, keeping it sorted. The final `__all__` is:

```python
__all__ = [
    "ArcadeDBGrpcClient",
    "AsyncArcadeDBGrpcClient",
    "AsyncTransaction",
    "AsyncTransactionHandle",
    "Auth",
    "InsecureChannelError",
    "InsertStreamRequest",
    "Transaction",
    "TransactionHandle",
    "__version__",
    "bearer_auth",
    "create_client",
    "messages",
    "password_auth",
]
```

- [ ] **Step 6: Run to verify it passes**

```bash
uv run pytest packages/driver-grpc/tests -v
```

Expected: all pass (9 async + the 27 from Tasks 3-7).

- [ ] **Step 7: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy
cd .. && git add python/ && git commit -m "feat(python-grpc): the async facade"
```

---

### Task 9: Public surface and the package README

**Files:**
- Create: `python/packages/driver-grpc/tests/test_public_surface.py`, `packages/driver-grpc/README.md`

**Interfaces:**
- Consumes: the finished `__all__` from Task 8.
- Produces: nothing later tasks import.

- [ ] **Step 1: Write the public-surface test**

Create `packages/driver-grpc/tests/test_public_surface.py`:

```python
import arcadedb_driver_grpc

EXPECTED_SURFACE = {
    "ArcadeDBGrpcClient",
    "AsyncArcadeDBGrpcClient",
    "AsyncTransaction",
    "AsyncTransactionHandle",
    "Auth",
    "InsecureChannelError",
    "InsertStreamRequest",
    "Transaction",
    "TransactionHandle",
    "__version__",
    "bearer_auth",
    "create_client",
    "messages",
    "password_auth",
}


def test_all_is_exactly_the_documented_surface() -> None:
    # Changing this set is a deliberate API decision, not a refactor. If this test
    # fails, update EXPECTED_SURFACE and the README's API section together.
    assert set(arcadedb_driver_grpc.__all__) == EXPECTED_SURFACE


def test_all_is_sorted_and_free_of_duplicates() -> None:
    assert arcadedb_driver_grpc.__all__ == sorted(set(arcadedb_driver_grpc.__all__))


def test_every_name_in_all_actually_resolves() -> None:
    for name in arcadedb_driver_grpc.__all__:
        assert hasattr(arcadedb_driver_grpc, name), f"__all__ names {name}, which does not exist"


def test_the_generated_package_is_not_part_of_the_public_surface() -> None:
    # `messages` is the PUBLIC alias for the generated message module, and it is stable
    # across contract bumps precisely because generate-grpc.sh normalises the proto
    # filename. `_generated` itself must never be re-exported: that path is private, and
    # exporting it would make its layout part of this package's API.
    assert "_generated" not in arcadedb_driver_grpc.__all__
    assert not any(
        name.startswith("_") and name != "__version__" for name in arcadedb_driver_grpc.__all__
    )


def test_messages_exposes_the_data_plane_types() -> None:
    for name in ("StreamQueryRequest", "InsertChunk", "InsertSummary", "GrpcRecord", "TransactionContext"):
        assert hasattr(arcadedb_driver_grpc.messages, name)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest packages/driver-grpc/tests/test_public_surface.py -v`
Expected: 5 passed. If `__all__` is unsorted or a name is missing, fix `__init__.py` — not the test's expectations, unless the surface change is deliberate.

- [ ] **Step 3: Write the README**

Create `packages/driver-grpc/README.md`, modelled on `packages/driver/README.md` and `typescript/packages/driver-grpc/README.md`. It **must** cover, at length rather than in passing:

1. Install, quick start (sync and async), and the `host:port` target form.
2. `create_client`'s insecure guard: why a plaintext password over an insecure channel is refused, and that `insecure=True` is the explicit opt-in.
3. Why auth is a channel interceptor, and therefore why `client.raw` is authenticated too.
4. `stream_query`: that it flattens batches, and that it picks no `retrieval_mode` or `batch_size` default on purpose.
5. `insert_stream`: the full envelope contract, the `options.database` mirroring and the #6597 reasoning, and why an empty stream is one empty final chunk rather than an error.
6. `transaction`: the commit-flag check, the binding override, and why `insert_stream` and `bulk_insert` are **not** on the handle while #6607 is open.
7. Why `grpc.RpcError` is not wrapped into a package-specific error.
8. A "Contract version and compatibility" section with the `[tool.arcadedb] server-version` snippet and this table:

```markdown
| `arcadedb-driver-grpc` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |
```

- [ ] **Step 4: Commit**

```bash
cd .. && git add python/ && git commit -m "docs(python-grpc): package README and the public-surface test"
```

---

### Task 10: End-to-end against a real server

**Files:**
- Create: `python/e2e/test_grpc.py`
- Modify: `python/e2e/conftest.py`, `python/pyproject.toml`

**Interfaces:**
- Consumes: the finished sync facade.
- Produces: nothing later tasks import.

**Two operational facts that cost real time during M1b. Both are load-bearing:**
1. **The gRPC plugin is not enabled by default.** `SERVER_PLUGINS` defaults to empty, so without `-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin` nothing listens on 50051 at all.
2. **The root password must be at least 8 characters.** A shorter one kills the server at startup with `ServerSecurityException: User password too short (<8 characters)`, and the only visible symptom is a closed port 50051 — which reads exactly like "gRPC is broken in this image" rather than "the server refused to start".

- [ ] **Step 1: Add the test-only dependency**

In `python/pyproject.toml`, the workspace root already depends on `arcadedb-driver`. Confirm it is still listed under `[project] dependencies`; the e2e suite imports it to create the database over HTTP. Add nothing to `packages/driver-grpc/pyproject.toml` — the runtime package must stay standalone.

- [ ] **Step 2: Add the gRPC container fixture**

Append to `python/e2e/conftest.py`:

```python
# Image pin: kept independent of `base_url`'s pin above, even though both currently name
# the same tag. They agree because each is pinned to the release its own contract came
# from, not because this one inherits the other's reasoning. The .proto and the OpenAPI
# spec are separate artifacts published from the same server release; if they ever stop
# moving together, these two pins move apart, and nothing here should make that awkward.
GRPC_DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.9.1"
GRPC_ARCADEDB_IMAGE = os.environ.get("ARCADEDB_DOCKER_IMAGE", GRPC_DEFAULT_ARCADEDB_IMAGE)
GRPC_DB_NAME = "clienttestgrpc"


@pytest.fixture(scope="session")
def grpc_server() -> Iterator[tuple[str, str]]:
    """Starts an ArcadeDB container with the gRPC plugin on.

    Yields `(http_base_url, grpc_target)`.

    A SEPARATE container from `base_url`'s, not an extension of it: sharing would let a
    gRPC plugin failure redden the HTTP suite, which has nothing to do with gRPC.

    Two facts that are easy to get wrong and hard to diagnose:

    - The GRPC plugin is NOT enabled by default. `SERVER_PLUGINS` defaults to empty, so
      without the `-Darcadedb.server.plugins=...` below, nothing listens on 50051 at all.
    - `ROOT_PASSWORD` must be at least 8 characters. A shorter one kills the server at
      startup with `ServerSecurityException: User password too short (<8 characters)`,
      and the only visible symptom is a closed port 50051 - which reads exactly like
      "gRPC is broken in this image" rather than "the whole server refused to start".
      `playwithdata` is 12, well clear of the limit.
    """
    container = (
        DockerContainer(GRPC_ARCADEDB_IMAGE)
        .with_env(
            "JAVA_OPTS",
            f"-Darcadedb.server.rootPassword={ROOT_PASSWORD} "
            "-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin",
        )
        .with_exposed_ports(2480, 50051)
    )
    with container:
        host = container.get_container_host_ip()
        http_url = f"http://{host}:{container.get_exposed_port(2480)}"
        _wait_until_ready(http_url)
        # This line appears only once the GRPC plugin has finished starting and is
        # actually listening, so it is the signal - not the open TCP port.
        wait_for_logs(container, r"gRPC server started on 0\.0\.0\.0:50051", timeout=90)
        yield http_url, f"{host}:{container.get_exposed_port(50051)}"


@pytest.fixture(scope="session")
def grpc_database(grpc_server: tuple[str, str]) -> str:
    """Creates the gRPC test database and its schema over HTTP.

    No data-plane RPC creates a database and the admin service is out of scope for this
    package, so setup goes over HTTP - exactly as `typescript/e2e/grpc.test.ts` does.
    """
    from arcadedb_driver import ArcadeDBServer, basic_auth

    http_url, _ = grpc_server
    with ArcadeDBServer(base_url=http_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        # Issued through the pooled httpx client rather than the generated
        # `execute_server_command` operation, for the reason the `database` fixture above
        # documents at length: the contract declares this endpoint's 200 response as
        # `QueryResponse` (`result: array`), but the server answers `create database`
        # with `{"result": "ok"}` - a string - and the generated model's `from_dict`
        # iterates that string character by character and raises `ValueError`.
        response = srv.raw.get_httpx_client().post(
            "/api/v1/server",
            json={"command": f"create database {GRPC_DB_NAME}", "language": "sql"},
        )
        assert response.is_success, response.text
        srv.db(GRPC_DB_NAME).command(
            language="sql", command="CREATE VERTEX TYPE Person IF NOT EXISTS"
        )
    return GRPC_DB_NAME
```

Add this import to `e2e/conftest.py`'s top-level imports:

```python
from testcontainers.core.waiting_utils import wait_for_logs
```

`ArcadeDBServer` and `basic_auth` are imported inside the fixture, matching how the existing `database` fixture does it.

- [ ] **Step 3: Write the e2e tests**

Create `python/e2e/test_grpc.py`:

```python
"""End-to-end tests for arcadedb-driver-grpc against a real ArcadeDB server."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from arcadedb_driver_grpc import ArcadeDBGrpcClient, InsertStreamRequest, create_client, messages
from arcadedb_driver_grpc.auth import password_auth

from .conftest import ROOT_PASSWORD


@pytest.fixture
def client(grpc_server: tuple[str, str], grpc_database: str) -> Iterator[ArcadeDBGrpcClient]:
    _, target = grpc_server
    with create_client(
        target,
        auth=password_auth("root", ROOT_PASSWORD, grpc_database),
        # The container speaks plaintext gRPC, so the guard has to be opted out of
        # explicitly. That it must be opted out of here IS the guard working.
        insecure=True,
    ) as grpc_client:
        yield grpc_client


def _person(name: str) -> messages.GrpcRecord:
    return messages.GrpcRecord(
        type="Person", properties={"name": messages.GrpcValue(string_value=name)}
    )


def _names(client: ArcadeDBGrpcClient, database: str, marker: str) -> list[str]:
    rows = client.stream_query(
        messages.StreamQueryRequest(
            database=database, language="sql", query=f"SELECT FROM Person WHERE name LIKE '{marker}%'"
        )
    )
    return sorted(r.properties["name"].string_value for r in rows)


def test_password_auth_reaches_the_server(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    response = client.raw.ExecuteQuery(
        messages.ExecuteQueryRequest(database=grpc_database, language="sql", query="SELECT FROM Person")
    )
    assert response is not None


def test_stream_query_returns_rows(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"sq{uuid.uuid4().hex[:8]}"
    client.raw.ExecuteCommand(
        messages.ExecuteCommandRequest(
            database=grpc_database, language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
        )
    )
    assert _names(client, grpc_database, marker) == [f"{marker}-a"]


def test_insert_stream_inserts_rows(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    # THE test for the options.database mirroring. Against a real 26.9.1 server, an
    # insert_stream that does not mirror `database` into `options` fails at the deferred
    # commit with "Invalid database name: name is required". If this test fails that way,
    # the mirroring in stream.py has been removed - restore it, do not work around it.
    marker = f"is{uuid.uuid4().hex[:8]}"
    summary = client.insert_stream(
        InsertStreamRequest(
            database=grpc_database,
            options=messages.InsertOptions(target_class="Person"),
            chunks=[[_person(f"{marker}-a"), _person(f"{marker}-b")], [_person(f"{marker}-c")]],
        )
    )
    assert summary.inserted == 3
    assert _names(client, grpc_database, marker) == [f"{marker}-a", f"{marker}-b", f"{marker}-c"]


def test_an_empty_insert_stream_is_accepted(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    summary = client.insert_stream(
        InsertStreamRequest(
            database=grpc_database, options=messages.InsertOptions(target_class="Person"), chunks=[]
        )
    )
    assert summary.inserted == 0
    assert summary.failed == 0


def test_transaction_commits(client: ArcadeDBGrpcClient, grpc_database: str) -> None:
    marker = f"tc{uuid.uuid4().hex[:8]}"
    with client.transaction(grpc_database) as tx:
        tx.execute_command(
            messages.ExecuteCommandRequest(language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'")
        )
    assert _names(client, grpc_database, marker) == [f"{marker}-a"]


def test_transaction_rolls_back(
    grpc_server: tuple[str, str], grpc_database: str, client: ArcadeDBGrpcClient
) -> None:
    # Asserts the MECHANISM, not only the row absence: an insert that silently failed
    # would also leave no rows and would pass a row-absence-only assertion. So this
    # test proves RollbackTransaction was actually issued and CommitTransaction was not.
    marker = f"tr{uuid.uuid4().hex[:8]}"
    sentinel = RuntimeError("boom")
    with pytest.raises(RuntimeError) as caught:  # noqa: PT012
        with client.transaction(grpc_database) as tx:
            tx.execute_command(
                messages.ExecuteCommandRequest(
                    language="sql", command=f"INSERT INTO Person SET name = '{marker}-a'"
                )
            )
            raise sentinel

    assert caught.value is sentinel
    assert _names(client, grpc_database, marker) == []
```

Then add one more test using `bearer_auth`, so both auth paths are exercised end to end. Obtain a token over HTTP with the HTTP driver's login helper and build a second client with `bearer_auth(token)`; if the server's data plane rejects the HTTP-issued token, record that finding in the README's auth section rather than deleting the test — it is a real compatibility fact worth documenting.

- [ ] **Step 4: Run the e2e suite**

Run: `uv run pytest e2e/test_grpc.py -v` (Docker required)
Expected: all pass. If port 50051 refuses connections, re-read the two facts above before debugging anything else.

- [ ] **Step 5: Commit**

```bash
cd .. && git add python/ && git commit -m "test(python-grpc): end-to-end suite against a real server"
```

---

### Task 11: CI

**Files:**
- Modify: `.github/workflows/ci-python.yml`, `.github/workflows/contract-watch.yml`

- [ ] **Step 1: Add the second drift gate**

In `ci-python.yml`'s `build` job, after the existing "Regenerate and verify no drift" step, add:

```yaml
      - name: Regenerate the gRPC client and verify no drift
        working-directory: python
        run: |
          ./scripts/generate-grpc.sh

          GEN=packages/driver-grpc/src/arcadedb_driver_grpc/_generated

          # Catches a MODIFIED generated file (existing path, changed content).
          git diff --exit-code -- "$GEN"

          # Catches an ADDED or RENAMED generated file: `git diff` above is blind to
          # untracked paths, so a contract that introduced a new message would leave the
          # diff check green while the new file went uncommitted.
          if [[ -n "$(git status --porcelain -- "$GEN")" ]]; then
            echo "Generated gRPC output changed - commit the regenerated output:" >&2
            git status --porcelain -- "$GEN" >&2
            exit 1
          fi
```

Add a comment above it recording why this gate is **two**-part while the HTTP one is three:

```yaml
      # Two-part, not three. The HTTP gate's third part exists because
      # openapi-python-client drops an endpoint it cannot model, warns, and exits 0, so
      # neither check above can see an endpoint that was never generated. protoc has no
      # such failure mode - it fails loudly - so a third check here would imply a risk
      # that does not exist.
```

Also add `contracts/**` — already present — and confirm the `paths` filters need no change: `python/**` covers the new package and `scripts/**` covers the new resolver.

- [ ] **Step 2: Extend contract-watch**

In `.github/workflows/contract-watch.yml`, find where it regenerates the Python client and add the gRPC regeneration beside it, so a contract change is verified against all three clients rather than two.

- [ ] **Step 3: Verify locally**

```bash
cd python && ./scripts/generate-grpc.sh && git status --porcelain -- packages/driver-grpc/src/arcadedb_driver_grpc/_generated
```

Expected: empty output. Non-empty means the committed generated tree does not match what the script produces — commit the regenerated output.

- [ ] **Step 4: Commit**

```bash
cd .. && git add .github/ && git commit -m "ci: drift-gate the Python gRPC client"
```

---

### Task 12: Release

**Files:**
- Modify: `.github/workflows/publish-python.yml`

- [ ] **Step 1: Add the `package` input**

Parameterise the workflow with a `package` input (`driver` / `driver-grpc`) exactly as `publish.yml` was parameterised in `3c7ba9d`. Read that commit first: `git show 3c7ba9d -- .github/workflows/publish.yml`.

Add a comment recording why this is one parameterised workflow rather than two files:

```yaml
# Parameterised rather than duplicated into a sibling workflow for the same reason
# publish.yml is: PyPI keys a trusted publisher on the workflow FILENAME, so both
# packages naming this one file means one thing to configure and cross-check instead
# of two. Each package still needs its own trusted publisher.
#
# Unlike npm, PyPI supports PENDING publishers: arcadedb-driver-grpc's can be
# configured before the package exists on the index, so its first publish needs no
# bootstrap token.
```

- [ ] **Step 2: Re-verify the version agreement for either package**

The existing step that checks the dispatch input against the package version and the contract's version must read from the selected package's `pyproject.toml`. Generalise the path rather than duplicating the step.

- [ ] **Step 3: Add the dist assertion**

Assert the built wheel contains the four generated files:

```bash
python -m zipfile -l dist/*.whl | grep -E 'arcadedb_server_pb2(_grpc)?\.(py|pyi)$'
```

Expected: four matches. Add a comment noting why this is simpler than npm's equivalent:

```yaml
# Simpler than publish.yml's dist assertion for driver-grpc, which derives the expected
# filename from arcadedb.serverVersion because its generated module is version-stamped.
# This one is not: generate-grpc.sh normalises the proto filename, so these names are
# constant and a regenerate overwrites rather than accumulates. The stale-module hazard
# npm's derived-name check exists to catch cannot occur here.
```

- [ ] **Step 4: Validate the workflow parses**

```bash
gh workflow view publish-python.yml
```

Do **not** dispatch it. Publishing is a human decision.

- [ ] **Step 5: Commit**

```bash
git add .github/ && git commit -m "ci: let publish-python.yml publish either Python package"
```

---

### Task 13: Repository documentation

**Files:**
- Modify: `python/CLAUDE.md`, `CLAUDE.md`, `README.md`

- [ ] **Step 1: Update `python/CLAUDE.md`**

Add to the Commands block:

```bash
./scripts/generate-grpc.sh   # regenerate the gRPC client from contracts/
```

Add a section explaining the two non-obvious codegen facts (normalised filename, package-shaped staging path) and pointing at the script's comment block for the full reasoning. Extend the "Two facades, one generated layer" section to say it now describes two packages.

- [ ] **Step 2: Update the root `CLAUDE.md`**

- Mention `arcadedb-driver-grpc` where the Python workspace is described.
- Add `scripts/resolve-proto-contract.sh` to the contracts command list.
- Update the `ci-python.yml` bullet: the drift gate is now two gates, and the gRPC one is two-part for a stated reason.
- Update the `publish-python.yml` bullet: it now publishes one package per dispatch, chosen by a `package` input, and note PyPI's pending-publisher advantage over npm.
- Note that `adopt-contract-version.sh` needed no change for the Python gRPC client because the generated module is unstamped.

- [ ] **Step 3: Update the root `README.md`**

Add the new package to whatever table or list enumerates the clients, with its PyPI name and a one-line description.

- [ ] **Step 4: Full verification**

```bash
cd python
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
./scripts/generate.sh && ./scripts/generate-grpc.sh && cd .. && git status --porcelain
```

Expected: every command passes and `git status --porcelain` is empty. An empty status is the drift gate's own question answered locally.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "docs: document arcadedb-driver-grpc across the repository"
```
