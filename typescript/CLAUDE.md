# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Scope: the TypeScript workspace. See the repository root `CLAUDE.md` for the contract pipeline,
the drift gate, and the release workflows that govern this directory.

## Commands

Run everything from `typescript/`.

```bash
npm ci                     # install (Node >= 20)
npm run generate           # regenerate both clients from contracts/ (http + grpc)
npm run typecheck          # tsc --build across the project references
npm run lint               # eslint
npm test                   # vitest run — unit tests only, offline, no Docker
npm run e2e                # vitest against a real ArcadeDB container (Docker required, Node >= 22.22)

npx vitest run packages/driver/test/data.test.ts          # a single test file
npx vitest run -t "rolls back"                            # a single test by name
npx vitest run --config e2e/vitest.config.ts e2e/grpc.test.ts   # a single e2e file
```

`vitest.config.ts` excludes `e2e/**` so `npm test` never pulls a container; the e2e suite has its
own config with 60s test / 90s hook timeouts. Both e2e suites pin `arcadedata/arcadedb:26.10.1-SNAPSHOT` and
honour `ARCADEDB_DOCKER_IMAGE` to override it (the smoke job in `ArcadeData/arcadedb` sets it to
the image built from the server commit under review). The gRPC suite must start the server with
`-Darcadedb.server.plugins=GRPC:...` — the plugin is off by default — and the root password must
be at least 8 characters or the server refuses to start, with a closed port 50051 as the only
symptom.

Packages build via `prepack` (`tsc --build`), which is what puts `dist/` in the tarball. There is
no separate `build` script.

## Generation

- `generate:http` — `openapi-typescript` over the path printed by
  `../scripts/resolve-openapi-contract.sh` → `packages/driver/src/generated/schema.ts`.
- `generate:grpc` — `buf generate --template buf.gen.yaml ..` (the module is the **root**
  `buf.yaml`) → `packages/driver-grpc/src/gen/arcadedb-server-<version>_pb.ts`.

The gRPC output filename embeds the contract version, so a contract bump creates a *new* file
beside the old one rather than modifying it. `src/index.ts` imports that version-stamped path
directly; `scripts/adopt-contract-version.sh` at the repo root is what rewrites the import and
deletes the retired module. Never hand-edit `src/generated/` or `src/gen/` — both are excluded
from eslint and both are checked by CI's drift gate.

## Two packages, deliberately different

`packages/driver` (`@arcadedb/driver`, HTTP) and `packages/driver-grpc` (`@arcadedb/driver-grpc`,
gRPC) share one toolchain and one CI job but are independent npm packages. Both are ESM-only,
Node >= 20, and record the server release they were generated against in
`package.json`'s `arcadedb.serverVersion`.

Their asymmetries are intentional and documented in each package's README:

- **Errors.** The HTTP facade throws `ArcadeDBError`; `server.raw` (openapi-fetch) never throws
  and returns `{ data, error }`. The gRPC client throws Connect's `ConnectError`. Do not
  "harmonise" these — translating one transport's error into the other's shape drops information.
- **Browser support.** The HTTP client works in a browser; the gRPC client cannot and will not
  until the server grows a gRPC-Web or Connect handler.
- **Admin service.** `ArcadeDbAdminService` is deliberately not wrapped by the gRPC package (it
  authenticates from a field inside the request message, not from metadata). Admin operations live
  on the HTTP client.

## HTTP client structure

`src/index.ts` holds `ArcadeDBServer` / `ArcadeDBDatabase` and the `db.ts` / `db.grafana` /
`db.promql` namespaces; `src/facade/*.ts` holds the per-area request functions;
`src/internal/unwrap.ts` is the single bridge from openapi-fetch's `{ data, error }` to the
throwing facade. `unwrap` lives in `internal/` rather than being re-exported from `index.ts`
specifically to break the `index.ts` ↔ `facade/*.ts` import cycle.

The three namespaces load their implementation with a **dynamic `import()`**. That is a
tree-shaking contract, not a style choice: `test/treeshake.test.ts` bundles a data-plane-only
entry with esbuild `splitting` and asserts the time-series, Grafana, and PromQL route markers are
absent. Converting one of those to a static import silently breaks that guarantee — and the test.

Transactions thread a session id: `transaction()` begins one, constructs a second
`ArcadeDBDatabase` carrying `sessionId`, and every call through *that* handle sends
`arcadedb-session-id`. The commit/rollback error contract (the callback's error always wins; a
failed rollback is attached as `cause` only when `cause` is unset; a failed commit still issues a
best-effort rollback) is spelled out in the doc comment on `transaction` — preserve it.

## gRPC client structure

`src/index.ts` builds the Connect transport and composes `raw` (the generated client) with three
wrappers: `streamQuery` (`src/stream.ts`), `insertStream` (`src/stream.ts`), and `transaction`
(`src/transaction.ts`). Everything else is reached through `raw`.

Points to preserve when editing:

- `createClient` refuses `passwordAuth` over a non-TLS `baseUrl` unless `insecure: true`. The
  check is `protocol !== "https:"`, not `=== "http:"`, because `new URL("localhost:50051")` parses
  with protocol `"localhost:"`.
- `insertStream` owns only the envelope bookkeeping — one stable `session_id`, `chunk_seq` from 1,
  `database` on the first chunk, `last` on the final one — plus mirroring `options.database` as a
  workaround for servers without the fix for `ArcadeData/arcadedb#6597`. An empty `chunks`
  iterable is valid, not an error.
- `streamQuery` flattens batches into rows and nothing else; `retrievalMode` and `batchSize` stay
  the caller's choice.
- `TransactionHandle` excludes `bulkInsert` and `insertStream` because the server commits those
  independently of the transaction (`ArcadeData/arcadedb#6607`).

## Lint configuration

Type-checked linting (`recommendedTypeChecked`) is scoped to `packages/*/src/**` only — both
packages' `tsconfig.json` include `src` alone, and test/e2e files deliberately do things that trip
type-aware rules. The rule that matters here is `no-floating-promises`: these libraries are mostly
promise plumbing, and a dropped `await` is the central hazard.
