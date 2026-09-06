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
