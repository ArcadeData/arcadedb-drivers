# M3b: `arcadedb-driver-grpc`, the Python gRPC driver

**Status:** design approved, plan pending
**Date:** 2026-09-04
**Parent:** ArcadeData/arcadedb Epic #4894, milestone M3b
**Predecessors:** M1b (`@arcadedb/driver-grpc`, merged as `e1f3942`) and M3 (`arcadedb-driver`,
merged as `be943cd`).

## 1. Scope

M3b ships `arcadedb-driver-grpc`: a thin client over ArcadeDB's gRPC proto for Python, covering the
data plane only. It is the Python sibling of `@arcadedb/driver-grpc` and the gRPC sibling of
`arcadedb-driver`.

The facade is three wrappers - `stream_query`, `insert_stream`, `transaction` - in both a sync and
an async flavour. The other 11 data-plane RPCs and all 9 admin RPCs are reachable through the
generated stub, which the package exports but does not wrap.

## 2. Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Runtime library | `grpcio` + `protobuf`; generated with `grpcio-tools` and `mypy-protobuf` |
| 2 | Facades | Both sync and async, over one generated layer |
| 3 | Codegen driver | Local `python -m grpc_tools.protoc`, not `buf` |
| 4 | Facade width | `stream_query`, `insert_stream`, `transaction` only |
| 5 | Transaction idiom | A context manager, not TypeScript's callback |
| 6 | Admin service | Excluded from the hand-written surface; reachable via the generated stub |
| 7 | Code sharing with `arcadedb-driver` | None at runtime; a test-only dependency in the e2e suite |

Inherited from M1b and M3 and not revisited: generated code committed and drift-gated, publishing
behind a manual `workflow_dispatch`, independent semver with a recorded contract version, no
browser or alternative-runtime targets.

Decisions 1, 3 and the absence of a version-stamping problem resolve the three open questions
section 12 of the M3 design recorded for this milestone. Each was settled by probe, not by
argument; section 4 records what the probes found.

## 3. Why the facade is this narrow

The same reasoning M1b set out, and it holds unchanged in Python.

**Transactions are why this is not a zero-facade package.** `BeginTransaction` returns a
`transaction_id` that must be threaded into the `TransactionContext` of every subsequent request and
ended on both the success and failure paths. The 2026-07 gRPC audit filed transaction hijack, silent
data loss and leaked transactions as #5040 through #5042 on exactly that surface. A client that made
transactions easy to get wrong would reintroduce that class of defect by ergonomics.

**The admin service is excluded.** `arcadedb-driver` already covers discovery and lifecycle over
HTTP; its RPCs authenticate through a `DatabaseCredentials` field in the request message rather than
through metadata, so one interceptor cannot serve both planes; and its destructive RPCs are where
this surface has been most dangerous (#5039). Nothing is blocked - protoc still generates the admin
stub and a caller can use it directly. What is withheld is the implication that we designed and
tested a path for `DeleteUser`.

**`InsertBidirectional` and `GraphBatchLoad` stay with the generated stub.** A bidirectional stream
has no natural single-shape wrapper, since the caller produces and consumes at once, and flattening
it would hide backpressure the caller needs. `GraphBatchLoad` is the same client-streaming shape as
`InsertStream`, so adding it later is mechanical if demand appears. `BulkInsert` is unary and needs
nothing.

## 4. Four toolchain facts, each established by probe

None of these is a design preference. All four were verified against the real toolchain before this
document was written, because the M3 design's guesses about two of them were wrong.

**The version-stamped proto filename is fatal to Python codegen, not merely awkward.** protoc
converts `-` to `_` but treats `.` as a *directory separator*. Given
`contracts/arcadedb-server-26.9.1.proto` it writes `arcadedb_server_26/9/1_pb2.py`, and the service
stub it generates opens with:

```python
from arcadedb_server_26.9 import 1_pb2 as arcadedb__server__26_dot_9_dot_1__pb2
#   SyntaxError: invalid decimal literal
```

That output cannot be imported at all. Section 12 of the M3 design anticipated this as a *retirement*
problem - "M3b inherits the `_pb.ts` situation and `adopt-contract-version.sh` needs a Python
retirement step and an import-repointing pattern". It is not. The filename must be normalised before
protoc sees it, which means the generated module carries no version stamp, which means there is
nothing to retire and no import to repoint. M3b needs *less* from `adopt-contract-version.sh` than
M3 predicted, not more.

**Staging the normalised proto under its package path yields a correct import with no
post-processing.** protoc derives the generated import from the proto's path relative to `-I`. With
the contract staged as `arcadedb_driver_grpc/_generated/arcadedb_server.proto` and `-I` at the stage
root, the stub emits:

```python
from arcadedb_driver_grpc._generated import arcadedb_server_pb2
```

which is correct for an installed wheel. The naive invocation instead emits a bare
`import arcadedb_server_pb2`, which only resolves if the generated directory happens to be on
`sys.path`. Getting this right at generate time is what keeps the repository's "generated code is
never hand-edited" rule intact: the alternative is a `sed` pass over protoc's output.

**`grpcio-tools` ships no `protoc-gen-*` plugin binaries.** Version 1.83.1 exposes exactly one
console script, `python-grpc-tools-protoc` - a bundled protoc with the `python` and `grpc_python`
generators compiled in. This is why "drive codegen with `buf` using local plugins" is the most
expensive option rather than the tidiest: it would mean sourcing and pinning protoc plus a gRPC
Python plugin separately, a third toolchain to install in CI for output the other two approaches
already produce.

**Neither `grpcio` nor `protobuf` ships `py.typed`, and protoc types messages only.** protoc's
`--pyi_out` produces `arcadedb_server_pb2.pyi` but no `_pb2_grpc.pyi`, so the service stub is
untyped. Under this repository's `mypy --strict` that would make the client's `raw` attribute an
`Any` - the single most useful object in the package, untyped. `mypy-protobuf` fixes it: its
`--mypy_out` and `--mypy_grpc_out` plugins generate stubs for both, and the gRPC stub file declares
**two** classes, `ArcadeDbServiceStub` typed against `grpc` and `ArcadeDbServiceAsyncStub` typed
against `grpc.aio`. The two-facade design therefore gets its types generated and drift-gated, with
nothing hand-maintained. `grpc-stubs` covers `grpc` itself for the hand-written facade.

## 5. Package and toolchain

```
buf.yaml                                    # repo root: unchanged, still lint/breaking authority
contracts/
├── arcadedb-openapi-<ver>.json
└── arcadedb-server-<ver>.proto             # shared with @arcadedb/driver-grpc
scripts/
└── resolve-proto-contract.sh               # new, sibling of resolve-openapi-contract.sh
python/
├── scripts/generate-grpc.sh                # new, sibling of generate.sh
└── packages/
    ├── driver/                             # arcadedb-driver (HTTP)
    └── driver-grpc/                        # arcadedb-driver-grpc
        ├── pyproject.toml                  # [tool.arcadedb] server-version
        └── src/arcadedb_driver_grpc/
            ├── __init__.py                 # sync facade, create_client
            ├── aio.py                      # async facade
            ├── auth.py
            ├── errors.py
            ├── stream.py
            ├── transaction.py
            ├── py.typed
            └── _generated/
                ├── __init__.py             # hand-written, empty, permanently stable
                ├── arcadedb_server_pb2.py
                ├── arcadedb_server_pb2.pyi
                ├── arcadedb_server_pb2_grpc.py
                └── arcadedb_server_pb2_grpc.pyi
```

`generate-grpc.sh` locates the single `.proto` via `resolve-proto-contract.sh`, stages it into a
temporary directory as `arcadedb_driver_grpc/_generated/arcadedb_server.proto`, and runs
`uv run python -m grpc_tools.protoc` with `-I` at the stage root and
`--python_out --grpc_python_out --mypy_out --mypy_grpc_out`. `--pyi_out` is deliberately not passed:
mypy-protobuf's message stubs supersede protoc's, and both generators write the *same* path
(`arcadedb_server_pb2.pyi`), so passing both would have them contend for one file rather than
produce two.

`resolve-proto-contract.sh` exists for the reason `resolve-openapi-contract.sh` does: two contracts
must fail loudly rather than resolve by lexical order. `ci.yml`'s existing inline "exactly one
`.proto`" check could adopt it later; this milestone deliberately does not churn the TypeScript side
to make that happen.

`_generated/__init__.py` is hand-written - empty, with a comment saying so - because protoc emits no
package marker. It is the one hand-written file inside a generated directory in this repository. It
never changes, so it never trips the drift gate.

**`adopt-contract-version.sh` needs no changes.** It globs `python/packages/*/pyproject.toml` and
rewrites `server-version` there, asserting the key appears exactly once; its `PROTO_REF` pattern
already repoints proto filenames in the new package's prose; and because the generated module is
unstamped, its `PB_REF` retirement machinery has nothing to do here. A new package under
`python/packages/` is picked up for free. `python/pyproject.toml`'s ruff `extend-exclude` glob
(`packages/*/src/*/_generated`) already matches the new path too.

## 6. The client API

```python
from arcadedb_driver_grpc import create_client, password_auth

with create_client("localhost:50051", auth=password_auth("root", "playwithdata", "mydb"),
                   insecure=True) as client:
    for record in client.stream_query(request):
        ...
```

`create_client(target, *, auth=None, credentials=None, insecure=False)`, with the same signature in
`aio.py`, returns an object exposing `raw`, `stream_query`, `insert_stream` and `transaction`.

Three divergences from TypeScript, each forced by gRPC-Python rather than chosen:

**`target` is `host:port`, not a URL.** `grpc.insecure_channel("localhost:50051")` is the native
address form. Inventing a `base_url` to parse back into one would be ceremony.

**The insecure guard keys on channel credentials, not on a URL scheme.** `credentials=None` builds an
insecure channel; pairing `password_auth` with one raises `InsecureChannelError` unless
`insecure=True` is passed explicitly. This is a strictly more reliable check than TypeScript's, which
must defend against `new URL("localhost:50051").protocol` evaluating to `"localhost:"` rather than
`"http:"`. Python has no schemeless trap, because the channel type is stated rather than inferred.

**Both clients are context managers.** A `grpc.Channel` must be closed; Connect's transport needs no
teardown, so TypeScript has no counterpart. `with` / `async with` plus an explicit `close()`, which
also matches `arcadedb-driver`, already a context manager.

## 7. Auth

`bearer_auth(token)` sets `authorization: Bearer <token>`. `password_auth(user, password,
database=None)` sets `x-arcade-user`, `x-arcade-password` and, when given, `x-arcade-database`. The
same metadata keys the TypeScript interceptors write - the server reads metadata for the data plane
either way.

The mechanism differs. Each helper returns **one object implementing all four
`grpc.*ClientInterceptor` protocols** (unary-unary, unary-stream, stream-unary, stream-stream),
attached to the channel rather than passed per call. This is not stylistic: a channel interceptor
authenticates calls made through `raw` too, which is the property TypeScript gets for free by putting
its interceptor on the transport. Per-call `metadata=` would authenticate the three facade wrappers
and silently leave `raw` anonymous - and `raw` is where most of the 14 data-plane RPCs live: the
facade wraps five (`StreamQuery`, `InsertStream`, and the `Begin`/`Commit`/`Rollback` trio
`transaction()` drives), so 9 are reachable only through `raw` outside a transaction, and 3
(`BulkInsert`, `InsertBidirectional`, `GraphBatchLoad`) even inside one.

Call credentials (`grpc.metadata_call_credentials`) are deliberately not used. They require a secure
channel, and password auth over an insecure channel is exactly the configuration the e2e suite runs
against a test container.

`password_auth`'s object carries a `sends_plaintext_password = True` marker, the direct analogue of
TypeScript's `PLAINTEXT_PASSWORD` symbol. It is not public surface; it exists only so `create_client`
can tell a password interceptor from a bearer one.

## 8. The three wrappers

### `stream_query`

Server-streaming. Iterates the server's `QueryResult` batches and yields each `GrpcRecord`
individually, flattening the batching the wire protocol uses. Sync returns a generator, async an
async generator.

`retrieval_mode` (CURSOR / MATERIALIZE_ALL / PAGED) and `batch_size` pass through to the server
unchanged. This wrapper picks no defaults, because the three retrieval modes have materially
different memory and consistency behaviour that only the caller can judge.

### `insert_stream`

Client-streaming, and the wrapper that earns its keep. It owns the envelope bookkeeping a caller
would otherwise hand-roll:

- one `session_id` (a fresh UUID), stable for the whole stream
- `chunk_seq` starting at 1 and incrementing by 1
- `database` on the **first chunk only**, per the `.proto` contract
- `database` **also mirrored into `options.database` on that first chunk**
- `last=True` on the final chunk only

The mirroring is a compatibility workaround for servers predating the fix for
[ArcadeData/arcadedb#6597](https://github.com/ArcadeData/arcadedb/issues/6597). On 26.9.1 and every
earlier release the server builds its `InsertContext` from `InsertOptions.database` alone and never
reads `InsertChunk.database`, despite the proto documenting the latter as REQUIRED on the first
chunk. Without the mirror, every stream against such a server fails at the deferred commit with
`Invalid database name: name is required`, even though `database` was sent exactly as the contract
specifies. This was established empirically against a real server during M1b and ports verbatim.

An empty input sends a single chunk with zero rows and `last=True` rather than raising. A filter that
matched nothing is a legitimate outcome, not an error - the same principle both READMEs argue for
`truncated`. M1b verified against a real server that such a chunk is accepted cleanly and returns an
all-zero `InsertSummary`.

Determining which chunk is last needs one-element lookahead, so the caller's iterator is pulled
manually rather than with a plain `for`. The pull loop is wrapped in `try/finally` so that a stream
abandoned mid-flight still runs the caller's own cleanup - closing a file handle or a cursor - on
every exit path, not only on normal completion.

### `transaction`

A **context manager**, sync and async:

```python
with client.transaction("mydb") as tx:
    tx.execute_command(...)
```

This is a deliberate divergence from TypeScript's `transaction(database, fn)` callback.
`arcadedb-driver` already spells this `with db.transaction() as tx:`, and a caller moving between the
two Python drivers should not have to relearn the shape. The safety contract is unaffected: commit
and rollback both happen in `__exit__`.

The contract ports intact from M1b:

- `begin_transaction`, then **refuse to run the body** if the returned `transaction_id` is missing or
  blank. Running a caller's writes outside a real transaction while implying otherwise is the worst
  outcome available here.
- `tx` binds `database` and `transaction` onto every request, **overriding whatever the caller
  supplied**. That override is the mechanism, not an implementation detail: it is what makes
  #5040-#5042 unrepeatable. `tx` exposes `execute_query`, `execute_command`, `create_record`,
  `update_record`, `delete_record`, `lookup_by_rid`, and a bound `stream_query`.
- Body raises: roll back, then re-raise the original exception. A rollback failure attaches as
  `__cause__`. Python's exception chaining does natively what TypeScript's `err.cause` assignment has
  to do defensively, and there is no frozen-object case to guard against.
- Body succeeds: commit, then **read the `committed` flag and raise when it is false**. A server that
  has reaped the transaction answers `success=true, committed=false` with no error status at all;
  reporting success there would mean silently losing the caller's writes.
- Commit fails: issue a best-effort rollback, swallowing its own failure so the server does not hold
  the transaction open until it is reaped, and re-raise the commit error.

`insert_stream` and `bulk_insert` stay **off** the transaction handle while
[ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607) is open: they ignore
`TransactionContext`, so offering them there would imply a transactional guarantee the server does
not honour. This is the same call M1b made, and it flips when #6607 lands.

## 9. Errors

Server-side failures surface as `grpc.RpcError` (sync) and `grpc.aio.AioRpcError` (async),
**unwrapped**. This is the same deliberate asymmetry `python/CLAUDE.md` already documents for
TypeScript's `ConnectError` versus `ArcadeDBError`, and it is not an oversight to be tidied later.

There is no gRPC equivalent of the HTTP driver's `unwrap` because there is no envelope to unwrap. The
HTTP contract returns a 200 whose body may describe a failure, which is why `arcadedb-driver` has an
`_internal/unwrap.py` at all. A gRPC status code is not that shape.

`errors.py` therefore holds exactly one thing: `InsecureChannelError(ValueError)`, raised by
`create_client`'s guard. It is named rather than a bare `ValueError` so a caller can catch that
specific refusal without catching every other argument error.

## 10. Typing

Runtime dependencies: `grpcio`, `protobuf`. Dev dependencies: `grpcio-tools`, `mypy-protobuf`,
`grpc-stubs`.

`grpc-stubs` is needed because `grpcio` ships no `py.typed` and the hand-written facade touches
`Channel`, the four interceptor ABCs, and `RpcError` directly.

`_generated/` is excluded from mypy's *collection*, as the HTTP driver's is, but **not** with
`follow_imports = "skip"` - for the reason already written into `python/pyproject.toml`, which would
collapse every imported name to `Any` and erase exactly the typing mypy-protobuf exists to provide.
Unlike the HTTP driver, this milestone starts *without* `ignore_errors` on that module: mypy reads
only the `.pyi` on import, and mypy-protobuf targets strict mode. Adding `ignore_errors` is a
fallback if implementation proves it necessary, not a premise.

## 11. Testing

**Unit tests** run against a real in-process `grpc.server` (and `grpc.aio.server`) bound to port 0,
with a recording fake servicer. Not a mocked stub: gRPC has no `respx`, and mocking the stub would
skip the two properties most worth asserting - that channel interceptors actually put
`x-arcade-user` on the wire, and that `insert_stream` emits the exact
`session_id` / `chunk_seq` / first-chunk-`database` / `last` sequence. A fake servicer records what
genuinely arrived. Files mirror TypeScript's: `test_auth.py`, `test_stream.py`, `test_transaction.py`,
`test_public_surface.py`.

**E2E** lives in `python/e2e/test_grpc.py` with its own container fixture and its own image pin, kept
independent of the HTTP suite's the way `grpc.test.ts` keeps its pin independent of
`data-plane.test.ts`: the two agree because each is pinned to the release its own contract came from,
not because one inherits the other's reasoning. A separate container rather than an extended shared
fixture, so that a gRPC plugin failure cannot redden the HTTP suite.

Two operational facts cost real time to discover during M1b and port verbatim:

1. **The gRPC plugin is not enabled by default.** `SERVER_PLUGINS` defaults to empty, so without
   `-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin` nothing listens on
   50051 at all.
2. **The root password must be at least 8 characters.** A shorter one kills the server at startup
   with `ServerSecurityException: User password too short (<8 characters)`, and the only visible
   symptom is a closed port 50051 - which reads exactly like "gRPC is broken in this image" rather
   than "the whole server refused to start".

The fixture waits on both `/api/v1/ready` returning 204 and the log line
`gRPC server started on 0.0.0.0:50051`; the latter appears only once the plugin is actually
listening.

Database and schema setup goes over HTTP, since no data-plane RPC creates a database and the admin
service is out of scope. `arcadedb-driver` is therefore a **test-only** dependency of the e2e suite.
The runtime package remains standalone.

## 12. CI and release

**CI** extends `ci-python.yml` rather than adding a workflow. One uv workspace, one lockfile, one
ruff and mypy configuration, and the existing `paths: python/**` filter already covers the new
package - the same way `ci.yml` covers both TypeScript packages in one file. The added step is a
second regenerate-and-diff over `driver-grpc`'s `_generated`.

That gate is **two**-part, not three. `check_codegen_skips.py` exists because
`openapi-python-client` drops an endpoint it cannot model, warns, and exits 0, so neither the diff
nor the untracked-file check can see an endpoint that was never generated. protoc has no such failure
mode - it fails loudly - so there is nothing for a third check to catch, and adding one would be
ceremony that implies a risk that does not exist.

**Release** parameterises `publish-python.yml` with a `package` input (`driver` or `driver-grpc`)
rather than adding a sibling workflow. This is the precedent `3c7ba9d` set for npm, and it holds for
the same reason: PyPI also keys a trusted publisher on the workflow **filename**, so both packages
naming one file means one thing to configure and cross-check instead of two.

Two ways this is easier than npm's. PyPI supports pending publishers, so `arcadedb-driver-grpc`'s
trusted publisher can be configured before the package exists on the index and the first publish
needs no stored secret. And the dist assertion is simpler than `driver-grpc`'s on npm: the generated
module is unstamped, so the expected filenames are constant and a regenerate overwrites rather than
accumulates. The hazard npm's derived-name check exists to catch - `tsc --build` never removing
output whose source is gone, so `files: ["dist"]` shipping a retired module - cannot occur here.

**`contract-watch.yml`** regenerates and verifies both clients today; it gains the gRPC client as a
third.

## 13. Non-goals

- **The admin service facade** - see section 3.
- **`InsertBidirectional` and `GraphBatchLoad` wrappers** - reachable through the generated stub.
- **A dict-shaped ergonomics layer** over `GrpcRecord` / `GrpcValue`. Callers work with protobuf
  messages, as they do in the TypeScript client. This was considered and rejected as YAGNI; it can be
  added later without breaking the facade.
- **Sharing code with `arcadedb-driver`** - no `driver-core` package, matching M1b decision 4.
- **Driving Python codegen through `buf`** - see section 4.
- **`unasync` or any single-source sync/async generation** - two hand-written facades over one
  generated layer, as M3 established.
- **Automating the README compatibility tables** - the same human decision it is today.
- **A Python version matrix** beyond floor-and-current, until a version-specific bug appears.

## 14. Documentation

`python/packages/driver-grpc/README.md` is new, and carries its own compatibility table. The prose
conventions both existing READMEs follow apply: document the failure modes and deliberate
asymmetries at length - why `insert_stream` mirrors `database` into `options`, why an empty stream is
not an error, why `grpc.RpcError` is not wrapped, why `insert_stream` cannot join a transaction.
Those passages are load-bearing documentation, not decoration.

`python/CLAUDE.md`, the root `CLAUDE.md` and the root `README.md` are updated alongside.
