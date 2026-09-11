# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Scope: the Python workspace. See the repository root `CLAUDE.md` for the contract pipeline, the
drift gate, and the release workflows that govern this directory.

## Commands

Run everything from `python/`.

```bash
uv sync                    # install (Python >= 3.10; uv resolves and creates .venv)
./scripts/generate.sh      # regenerate the HTTP client from contracts/
./scripts/generate-grpc.sh # regenerate the gRPC client from contracts/
uv run mypy                # strict type-check (packages/driver/{src,tests}, packages/driver-grpc/{src,tests}, e2e)
uv run ruff check .        # lint
uv run ruff format --check .   # formatting check (use `ruff format .` without --check to fix)
uv run pytest              # unit tests only, offline, no Docker
uv run pytest e2e          # end-to-end tests against a real ArcadeDB container (Docker required)

uv run pytest packages/driver/tests/test_data.py -v   # a single test file
uv run pytest -k "rolls_back"                          # a single test by name (substring of the function name)
```

`pyproject.toml`'s `[tool.pytest.ini_options]` scopes `testpaths` to `packages/driver/tests` and
`packages/driver-grpc/tests`, and excludes `e2e/`, the same split `typescript/vitest.config.ts`
makes, so `uv run pytest` never starts a container. `-k` matches against the *test function name*,
not a literal string with spaces the way it might read - `-k "rolls back"` (space) does not filter
to `test_rolls_back_and_reraises_when_the_body_raises` the way it looks like it should; the test
names use underscores, so match on those.

The workspace root (`python/pyproject.toml`, `[tool.uv] package = false`) is not published; only
`packages/driver` and `packages/driver-grpc` are real packages. `uv sync` from `python/` installs
both the dev tooling and both packages in editable mode via `[tool.uv.workspace]` /
`[tool.uv.sources]`.

## Generation

`scripts/generate.sh` runs `openapi-python-client generate --meta none` against the contract
located by `../scripts/resolve-openapi-contract.sh`, writing into
`packages/driver/src/arcadedb_driver/_generated`. `--meta none` emits only the package body (no
project scaffolding of its own); the generated modules import each other relatively, which is what
lets the tree nest inside `arcadedb_driver` without rewriting a single import. **`_generated/` is
never hand-edited** - CI's drift gate regenerates from the committed contract and fails the build
if the result differs from what is checked in, the same rule the root `CLAUDE.md` states for the
whole repository.

The generator cannot model a non-JSON request body. When it meets one, it prints a warning, omits
the endpoint entirely, and **exits 0** - a skip leaves no trace in the generated tree, so `git
diff` cannot flag it and the drift gate alone cannot catch it. `scripts/check_codegen_skips.py`
exists specifically to close that gap: it re-runs the generator and asserts the set of skipped
operations equals a pinned allowlist (`POST /api/v1/batch/{database}`,
`POST /api/v1/ts/{database}/write`, `POST /api/v1/ts/{database}/prom/read`,
`POST /api/v1/ts/{database}/prom/write`). Adding an endpoint to that allowlist is a deliberate
decision to leave it unwrapped or hand-written - never a way to quiet the check. A contract change
that makes the generator skip something *not* on the list, or stops skipping something that *is*,
fails CI.

## gRPC generation

`scripts/generate-grpc.sh` runs `grpc_tools.protoc` against the contract located by
`../scripts/resolve-proto-contract.sh`, writing into
`packages/driver-grpc/src/arcadedb_driver_grpc/_generated`. Two facts about how it stages the
contract before invoking `protoc` are not arbitrary, and the script's own comment block spells out
the full reasoning - read that before touching the script:

1. **The contract is staged under a normalised filename.** `protoc` treats `.` in a proto's
   filename as a directory separator, not a literal dot, so handing it
   `contracts/arcadedb-server-26.10.1-SNAPSHOT.proto` directly produces an unimportable tree (an import line
   that is a `SyntaxError`). The script copies the contract to a fixed `arcadedb_server.proto`
   first. The happy side effect: the generated module carries no version stamp, unlike the
   TypeScript gRPC client's `arcadedb-server-<version>_pb.ts` - nothing to retire and no imports to
   repoint on a contract bump (see the root `CLAUDE.md`'s note on `adopt-contract-version.sh`).
2. **The staged path mirrors the Python package path.** `protoc` derives a generated module's
   cross-file import from the proto's path relative to its include root. Staging at that root would
   emit a bare `import arcadedb_server_pb2`, which only resolves if the generated directory happens
   to be on `sys.path`; staging under `arcadedb_driver_grpc/_generated/` instead makes `protoc` emit
   `from arcadedb_driver_grpc._generated import arcadedb_server_pb2`, the import that actually
   resolves once the package is installed as a wheel.

## Two facades, one generated layer

Both packages are shaped this way: a hand-written facade sits on top of one generated layer, and
the generated layer is never hand-edited.

`arcadedb-driver`'s synchronous facade and `aio.py` (`Async*`, asynchronous) are hand-written and
share the same generated `_generated/` tree - every generated operation emits both a
`sync_detailed` and an `asyncio_detailed` function returning the same `Response` shape, so the two
facades differ only in which call style they use and both funnel through the same
request-building and envelope-normalising helpers in `facade/data.py`. The sync/async split does
not line up with the module split: most sync classes live under `facade/` (`ArcadeDBDatabase` in
`__init__.py`, `Transaction` in `facade/transaction.py`) while their `Async*` twins live in
`aio.py`, but `facade/timeseries.py` and `facade/dashboards.py` each hold both their sync and
async classes side by side. Don't assume "facade/" means sync-only or "aio.py" means every async
class - check the class name, not the file it happens to be in.

The duplication between the sync and async facades is mechanical and deliberate.
[`unasync`](https://github.com/python-trio/unasync)-style single-source generation (write async,
strip `await`/`async` mechanically to produce sync) is a **non-goal** here: it would add a build
step and a second thing that can drift, to remove duplication that mypy already keeps honest -
`aio.py`'s docstring says the same. Keep both facades in sync by hand when one changes.

`arcadedb-driver-grpc` follows the same shape with a much thinner facade: `create_client` /
`aio.create_client` wrap only the RPCs the generated stub handles badly at the top level
(`stream_query`, `insert_stream`, `transaction`) - there is no `_generated`-tree
envelope-normalising step to mirror `facade/data.py`, because gRPC responses need no such
unwrapping (see that package's README, "Errors: `grpc.RpcError`, not a package-specific error").
`transaction()` itself returns a **second** wrapper, `TransactionHandle` (`transaction.py`), not a
bare route back to `raw`: every call made through it (`execute_query`, `execute_command`,
`create_record`, `update_record`, `delete_record`, `lookup_by_rid`, plus `stream_query` again,
bound this time) passes through `_bind`, which forcibly overwrites `request.database` and
`request.transaction` with the handle's own values, discarding whatever the caller had set on the
request object first. That override is the safety mechanism, not an incidental detail - it is
what makes transaction hijack, silent data loss, and leaked transactions
(ArcadeData/arcadedb#5040-#5042) unrepeatable through the handle, the gRPC-specific way
`arcadedb-driver`'s second `ArcadeDBDatabase` handle (see "The transaction contract" below) keeps a
transaction's calls separated from the outer handle's. Only three RPCs are ever reachable solely
through `raw` with no wrapper at any level: `BulkInsert`, `InsertBidirectional`, and
`GraphBatchLoad`. See `packages/driver-grpc/README.md` for its own sync/async split and its
transaction and streaming wrappers; it is not duplicated here.

## Deliberate asymmetries

- **The facade raises; `.raw` does not, for a non-2xx status.** Every facade method (`query`,
  `command`, `transaction`, `list_databases`, `exists`, `server_info`, `health`, `ready`, the
  `ts`/`grafana`/`promql` namespaces, ...) raises `ArcadeDBError` on a non-2xx response.
  `ArcadeDBServer.raw` - the generated `Client` - never raises for a non-2xx status; every one of
  its operations returns a `Response` whose `status_code` and `parsed` the caller inspects
  directly. That guarantee does not extend to a malformed *2xx* body: the generated model's
  `from_dict` can still raise out of the parser on a 200 response that does not match its declared
  shape - see "Two contract defects this milestone uncovered" below for a real one
  (`POST /api/v1/server`). This mirrors
  `@arcadedb/driver`'s `raw`/facade split (`{ data, error }` vs. throwing). Do not blur it: a
  caller mixing assumptions about which surface they are calling is the most common way to end up
  with either an unhandled exception or a silently ignored error.
- **`help_` matches the generated model.** `ArcadeDBError.help_` is spelled with a trailing
  underscore specifically because it must match the field name on the generated `ErrorResponse`
  model (reachable through `.raw`) - `help` alone would shadow the Python builtin, and giving the
  same field two different spellings across the package's two error surfaces would be worse than
  one consistently awkward name. See `errors.py`.
- **Omitting `timeout` disables timeouts entirely.** `ArcadeDBServer.__init__` and
  `AsyncArcadeDBServer.__init__` both declare `timeout: httpx.Timeout | None = None` and pass it
  straight to the generated `Client`, which forwards it to `httpx.Client`/`httpx.AsyncClient`. In
  httpx an explicit `timeout=None` means NO TIMEOUT, not "use httpx's 5-second default" - a caller
  who never passes `timeout` gets a client that can hang forever on a stalled connection. This is
  deliberate, not a bug to quietly fix by changing the default: the generated `Client` itself
  defaults `_timeout` to `None` and passes it through the same way, so a facade-only default would
  make `ArcadeDBServer` and `.raw` disagree against the same server, and it preserves parity with
  `@arcadedb/driver`, where `fetch` has no default timeout either. Pass an `httpx.Timeout` to
  bound requests.
- **`auth.py` is three lines where `auth.ts` is sixty; do not port the workaround.** `auth.ts`
  spends most of its length working around `btoa`: it treats input as Latin-1 and throws on
  anything above U+00FF, and a naive `String.fromCharCode(...bytes)` blows the call stack on a
  large credential, so the TypeScript client hand-rolls UTF-8 encoding and chunked
  Latin-1-to-`btoa` conversion. `base64.b64encode` takes raw bytes directly and has neither hazard
  - there is no problem here for that workaround to solve. If you find yourself porting
  `octetsToLatin1String` or its chunking logic into `auth.py`, stop; it is solving a problem that
  does not exist in Python.
- **The lazy-import/tree-shaking construct is deliberately absent.** `typescript`'s `db.ts` /
  `db.grafana` / `db.promql` namespaces load their implementation with a dynamic `import()`
  specifically so a bundler can tree-shake unused namespaces out of a browser bundle
  (`test/treeshake.test.ts` asserts this). Python has no bundler and no tree-shaking step - the
  construct would add indirection with no reader ever benefiting from it, so the equivalent
  namespaces here (`cached_property` on `ArcadeDBDatabase`) import and construct eagerly-on-first-
  access with no lazy-import wrapper. Do not add one; it would be cargo-culting a TypeScript
  concern into a runtime where it has no meaning.

## The transaction contract

`facade/transaction.py`'s `Transaction` (and `aio.py`'s `AsyncTransaction`) is a context manager
whose `__enter__`/`__aenter__` begins a server-side transaction and returns a **second**
`ArcadeDBDatabase`/`AsyncArcadeDBDatabase` carrying the session id - only calls made through that
second handle join the transaction; calls made through the outer handle used to open it
auto-commit individually, as if no transaction were open. The commit/rollback contract has three
clauses, each with its own test in `tests/test_transaction.py`:

1. **Clean exit → commit.** The block completes without raising: the transaction commits.
2. **Block raises → rollback, re-raise.** The transaction rolls back and the block's exception
   propagates. If the rollback *also* fails, its error is attached as `__cause__` on the block's
   exception rather than replacing it (the block's own error is what the caller asked about) -
   the attach is skipped if `__cause__` is already set (never overwrite a caller-set causal chain)
   and silently swallowed if attaching it fails outright (some libraries intern frozen sentinel
   errors that cannot take a new attribute).
3. **Commit itself fails.** A best-effort rollback is issued first (its own failure discarded -
   the commit error is what the caller needs to see) so the server-side session is not left open
   until `arcadedb.server.httpTxExpireTimeout` reaps it, then the commit's error is re-raised.

Preserve this contract exactly when touching `transaction.py` or `aio.py` - it is spelled out in
the doc comment on `Transaction`/`AsyncTransaction` for the same reason.

## `QueryEnvelope` is hand-written

`facade/data.py`'s `QueryEnvelope` normalises the generated `QueryResponse` into a stable public
type: it flattens each row out of `QueryResponseResultItem`'s additional-properties wrapper into a
plain `dict`, and defaults `limit` (to `-1`, uncapped), `returned` (to `0`), and `truncated` (to
`False`) when the server's response omits them - `QueryResponse` has no `required` list in the
contract, so all four fields are technically optional on the wire even though the current server
always sends them. This normalisation (the `_or` helper plus `to_envelope`) is applied **only** to
the data plane (`query`/`command`). The `ts`, `grafana`, and `promql` namespaces deliberately do
NOT get the same `Unset`-stripping treatment: `db.promql.*` passes the generated request/response
models through unaltered (`Unset` stays visible on optional fields, the same way `?: T | undefined`
stays visible in the TypeScript client), and `db.ts`/`db.grafana.query` bypass generated models
entirely for an unrelated reason (see below). Normalising the envelope is a data-plane ergonomics
decision, not a general policy to launder `Unset` out of every response this client returns.

## `CommandRequest.limit`

The generated `CommandRequest` model carries an optional `limit` field - the contract has it, the
generator produced it - but `ArcadeDBDatabase.command()` deliberately does not expose it (see
`build_command_request`'s docstring in `facade/data.py`). `@arcadedb/driver`'s `command()` does not
expose it either. Keeping the two clients' public surfaces identical matters more than shipping one
optional field early; adding it is additive and belongs in a change that does it for both clients
at once, not one that gets ahead of the other.

## Two contract defects this milestone uncovered

Both of the following look like bugs in this client until you know the cause is upstream. Both
have a "do not fix this back" quality: fixing them by routing through the generated models would
reintroduce the underlying defect's failure mode, just less visibly. Both are also the reason this
package is worth having, in one sense: **this Python client is the first ArcadeDB client that
validates responses at runtime.** `openapi-fetch`, which `@arcadedb/driver` is built on, performs
no runtime validation of its own - raw JSON passes straight through unexamined - so
`@arcadedb/driver` never noticed either defect below. `openapi-python-client` generates real
`attrs` models with real `from_dict` parsing, so this client is the one that actually exercises the
contract's declared shapes against the server's real responses, and found two places where they
disagree.

1. **Scalar values typed as `"type": "object"`.** The contract types time-series and Grafana
   scalar array elements as objects: `TimeSeriesRawResponse.rows[]`,
   `TimeSeriesAggregatedResponse.buckets[].values[]`, `TimeSeriesLatestResponse.latest[]`, and
   `GrafanaQueryResponse`'s per-element DataFrame values are all declared `"type": "object"`, when
   in reality each element is an ordinary scalar (a timestamp, a numeric measurement). The
   generated per-element model's `from_dict` calls `dict(value)` on every element, which raises
   `TypeError` on a real scalar. For `db.ts.query` this is silent and worse than a crash: the
   generated `oneOf` response parser in `query_time_series.py` catches that `TypeError` and falls
   through to the aggregated-response model, whose fields are all optional and so "parses"
   anything - every raw (non-aggregated) response would come back mis-typed as an empty-looking
   aggregated one instead of raising. `db.ts.latest` and `db.grafana.query` have no such fallback
   branch and would simply raise `TypeError` on any ordinary response. Consequently `db.ts.query`,
   `db.ts.latest`, and `db.grafana.query` are hand-written: each bypasses the generated response
   parsing, issues its request directly through the generated client's own pooled httpx client (so
   auth headers, timeout, and connection pooling still apply), and returns the parsed JSON body as
   `dict[str, Any]`. `db.promql.*` is unaffected - its response schemas do not have this shape, so
   it passes generated request/response models through unaltered like the rest of the data plane.
   Full detail lives in `facade/timeseries.py`'s module docstring and `facade/dashboards.py`'s.
   **Do not** route these three methods back through their generated operations without first
   fixing the contract's element typing - doing so would reintroduce the silent misclassification,
   not just the crash.

2. **`POST /api/v1/server` returns `{"result": "ok"}` - a string - where the contract declares**
   **`QueryResponse` with `result` typed as an array.** A real admin command (e.g. `create
   database`) answers with a bare string result, not the array shape the contract promises for
   this endpoint's 200 response, so the generated model's `from_dict` iterates that string
   character by character as if it were a list of row objects and raises `ValueError`. No facade
   method wraps `POST /api/v1/server` at all, so only `.raw` and `e2e/conftest.py`'s `database`
   fixture are affected. The fixture creates its test database through the pooled httpx client
   directly (`srv.raw.get_httpx_client().post(...)`), for exactly this reason - see its docstring.

Both defects are upstream contract inaccuracies. Both would be fixed by correcting the OpenAPI
contract's response schemas (element types in the first case, `POST /api/v1/server`'s `result`
type in the second) - not by changing anything in this client.

## Prose conventions

The root `CLAUDE.md`'s note on prose conventions applies here too: each package's README and the
code comments document failure modes and deliberate asymmetries at length (the two contract
defects above, why `exists` cannot prove absence, why `.raw` and the facade disagree about
raising, why `arcadedb-driver-grpc` raises `grpc.RpcError` directly rather than a package-specific
error). When you change behaviour in one of those areas, update the prose with it.
