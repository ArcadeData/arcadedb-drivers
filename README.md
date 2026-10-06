# arcadedb-drivers

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![TypeScript CI](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/ci.yml/badge.svg)](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/ci.yml)
[![Python CI](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/ci-python.yml/badge.svg)](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/ci-python.yml)
[![Go CI](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/ci-go.yml/badge.svg)](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/ci-go.yml)
[![Contract Watch](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/contract-watch.yml/badge.svg)](https://github.com/ArcadeData/arcadedb-drivers/actions/workflows/contract-watch.yml)

Language clients for [ArcadeDB](https://arcadedb.com)'s HTTP and gRPC APIs, generated from shared
OpenAPI and Protobuf contracts and kept in sync with them by CI.

The idea: one contract per API, many language clients. `contracts/` holds the OpenAPI spec and the
Protobuf `.proto` that every client in every language this repository will ever host is generated
from. A client's own package never hand-edits its generated types - the contract is the single
source of truth, and each client's build regenerates from it and fails the build (a "drift gate")
if the checked-in generated code and a fresh regeneration disagree.

## Packages

Six clients: an HTTP and a gRPC client each for TypeScript, Python and Go. Each links to its
registry page; the badge shows the version currently on that registry, so this table cannot go
stale the way a hardcoded number would. Go has no registry: its modules are fetched through the Go
module proxy and documented on pkg.go.dev, and neither is released yet - both join the lockstep at
the next release.

| | Package | API | Install |
|---|---|---|---|
| [![npm](https://img.shields.io/npm/v/@arcadedb/driver?logo=npm&label=)](https://www.npmjs.com/package/@arcadedb/driver) | [`@arcadedb/driver`](https://www.npmjs.com/package/@arcadedb/driver) | HTTP | `npm install @arcadedb/driver` |
| [![npm](https://img.shields.io/npm/v/@arcadedb/driver-grpc?logo=npm&label=)](https://www.npmjs.com/package/@arcadedb/driver-grpc) | [`@arcadedb/driver-grpc`](https://www.npmjs.com/package/@arcadedb/driver-grpc) | gRPC | `npm install @arcadedb/driver-grpc` |
| [![PyPI](https://img.shields.io/pypi/v/arcadedb-driver?logo=pypi&logoColor=white&label=)](https://pypi.org/project/arcadedb-driver/) | [`arcadedb-driver`](https://pypi.org/project/arcadedb-driver/) | HTTP | `pip install arcadedb-driver` |
| [![PyPI](https://img.shields.io/pypi/v/arcadedb-driver-grpc?logo=pypi&logoColor=white&label=)](https://pypi.org/project/arcadedb-driver-grpc/) | [`arcadedb-driver-grpc`](https://pypi.org/project/arcadedb-driver-grpc/) | gRPC | `pip install arcadedb-driver-grpc` |
| [![Go Reference](https://pkg.go.dev/badge/github.com/ArcadeData/arcadedb-drivers/go/arcadedb.svg)](https://pkg.go.dev/github.com/ArcadeData/arcadedb-drivers/go/arcadedb) | [`github.com/ArcadeData/arcadedb-drivers/go/arcadedb`](https://pkg.go.dev/github.com/ArcadeData/arcadedb-drivers/go/arcadedb) | HTTP | `go get github.com/ArcadeData/arcadedb-drivers/go/arcadedb@latest` |
| [![Go Reference](https://pkg.go.dev/badge/github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc.svg)](https://pkg.go.dev/github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc) | [`github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`](https://pkg.go.dev/github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc) | gRPC | `go get github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc@latest` |

Usage lives in each package's own README, linked from `## Layout` below. Every one of the six is
Apache-2.0 and generated from the contracts in `contracts/`.

## Layout

- `contracts/` - the OpenAPI and Protobuf contracts, fetched by `scripts/fetch-contract.sh` and
  committed.
- `typescript/` - two TypeScript/JavaScript clients, sharing one toolchain and one CI job:
  - [`@arcadedb/driver`](https://www.npmjs.com/package/@arcadedb/driver), the HTTP client.
    See `typescript/packages/driver/README.md` for usage.
  - [`@arcadedb/driver-grpc`](https://www.npmjs.com/package/@arcadedb/driver-grpc), the gRPC
    client. See `typescript/packages/driver-grpc/README.md` for usage, including why it has no
    browser build.
- `python/` - two Python clients, sharing one toolchain and one CI job:
  - [`arcadedb-driver`](https://pypi.org/project/arcadedb-driver/), the HTTP client.
    See `python/packages/driver/README.md` for usage.
  - [`arcadedb-driver-grpc`](https://pypi.org/project/arcadedb-driver-grpc/), the gRPC client.
    See `python/packages/driver-grpc/README.md` for usage, including why it raises
    `grpc.RpcError` directly rather than a package-specific error.
- `go/` - two Go clients, separate modules in one Go workspace, sharing one toolchain and one CI
  workflow:
  - [`github.com/ArcadeData/arcadedb-drivers/go/arcadedb`](https://pkg.go.dev/github.com/ArcadeData/arcadedb-drivers/go/arcadedb),
    the HTTP client. See `go/arcadedb/README.md` for usage, including why its releases are
    permanent.
  - [`github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc`](https://pkg.go.dev/github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc),
    the gRPC client. See `go/arcadedbgrpc/README.md` for usage, including why `RawAdmin` refuses a
    plaintext connection and why RPC failures are grpc-go status errors.
- `scripts/fetch-contract.sh` - fetches the OpenAPI contract from a released ArcadeDB version or a
  running Docker image, or copies the Protobuf contract out of a local `arcadedb` checkout, and
  writes the result into `contracts/`. See "The contracts" below.

Other language directories will appear here as siblings of `typescript/`, `python/` and `go/` as
this repository grows.

## The contracts

`scripts/fetch-contract.sh` has three modes:

```bash
scripts/fetch-contract.sh --release <tag>          # download + checksum-verify both release assets (OpenAPI and .proto)
scripts/fetch-contract.sh --image <image-reference> # start the image, fetch /api/v1/openapi.json (OpenAPI)
scripts/fetch-contract.sh --proto-from <checkout> [<version>]  # copy arcadedb-server.proto out of a local arcadedb checkout
```

In the `--release` and `--image` modes, the resulting OpenAPI spec is refused unless it is
structurally provably post-M0 (checked via a marker that cannot be true of any pre-M0 spec: the
`/api/v1/begin/{database}` 204 response carrying the `arcadedb-session-id` header). A version
string alone proves nothing about a spec's content, so the script does not trust one. The `.proto`
contract has no equivalent marker to check against. A released ArcadeDB attaches it to the GitHub
release beside the OpenAPI spec, so `--release` downloads both, verifies both checksums, and writes
neither unless both pass. A running server has no endpoint that serves the `.proto`, so for a
SNAPSHOT build, which has no release, `--proto-from` is a straight file copy out of a local
`arcadedb` checkout instead.

## Development

Each language client has its own toolchain and CI job; see that client's own README for build,
test, and release instructions. Nothing in this repository publishes a package automatically -
every release is a manual, human-triggered workflow dispatch.

## License

Apache-2.0.
