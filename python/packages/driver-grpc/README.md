# arcadedb-driver-grpc

A Python gRPC client for [ArcadeDB](https://arcadedb.com)'s data plane, generated from ArcadeDB's
protobuf contract (`contracts/arcadedb-server-*.proto`).

This package is currently scaffolding only: the generated `arcadedb_driver_grpc._generated`
package (`arcadedb_server_pb2`, `arcadedb_server_pb2_grpc`) is present and type-checked, but there
is no hand-written facade on top of it yet. See `arcadedb-driver` for the equivalent HTTP client's
facade shape, which this package will eventually mirror for the gRPC data plane.

Regenerate the `_generated/` tree with `scripts/generate-grpc.sh` from `python/`. As with
`arcadedb-driver`, generated code is never hand-edited: CI's drift gate regenerates from the
committed contract and fails if the result differs from what is checked in.
