# python/

Python clients for [ArcadeDB](https://arcadedb.com), generated from the contracts in
`../contracts/`.

- `packages/driver` - `arcadedb-driver`, the HTTP client. See
  [`packages/driver/README.md`](packages/driver/README.md) for installation, usage, and the
  contract defects it works around.
- `packages/driver-grpc` - `arcadedb-driver-grpc`, the gRPC client. See
  [`packages/driver-grpc/README.md`](packages/driver-grpc/README.md) for installation, usage, and
  why it raises `grpc.RpcError` directly rather than a package-specific error.

Developing in this directory (commands, code generation, facade layout, deliberate asymmetries
with the TypeScript sibling) is covered in [`CLAUDE.md`](CLAUDE.md).
