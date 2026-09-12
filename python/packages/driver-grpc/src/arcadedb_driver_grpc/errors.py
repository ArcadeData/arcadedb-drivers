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
    """Raised for either of two separate refusals to expose credentials over a channel
    that may be insecure.

    `create_client` raises it when a plaintext-password auth interceptor is paired with
    a channel that lacks real transport credentials and no `insecure=True` opt-in was
    given (issue #5048) - the password would travel in the auth interceptor's cleartext
    metadata. `ArcadeDBGrpcClient.raw_admin` (and its async twin) raises it, independently,
    on ACCESS when the same opt-in is missing: 42 of `ArcadeDbAdminService`'s 44 RPCs carry
    `DatabaseCredentials` INSIDE the request body, which the #5048 guard cannot see - that
    guard keys on a marker attached to the auth interceptor, not on request bodies - so
    `raw_admin` needed its own guard even with `bearer_auth`, `password_auth`, or no auth
    interceptor at all, and even for `Health`/`Ready`, which carry no credentials but share
    the same stub.

    Named rather than a bare `ValueError` so a caller can catch this specific
    refusal without catching every other argument error `create_client` may raise.
    """
