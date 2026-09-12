"""arcadedb#7309 argues server-side that a token-bearing response (`CreateApiToken`'s, in
particular) must be proved not to reach a log sink. On the client, all four sync
`intercept_*` methods on `_SyncAuthInterceptor`, and each of the four async
`_Async*AuthInterceptor` classes' single method, share one shape:
`return [await] continuation(_augment(client_call_details, self._extra), request[_iterator])`.
None of them has any reason to look at what `continuation` returns.

A test that only greps the module for `logging`/`print` would keep passing if a future edit
started reading a field off that return value (to log it, forward it, whatever) as long as it
didn't literally call one of those. `_AccessRecordingSentinel` below proves the stronger claim
directly: it stands in for whatever `continuation` hands back, and raises the instant anything
- any attribute at all - is read off it. Passing every one of the eight `intercept_*` methods a
sentinel and asserting it comes back untouched pins that these interceptors are pure
metadata-augmenting passthroughs, not "restate what a grep already found."

What this does NOT prove: `__getattribute__` is not invoked for implicit special-method
protocols Python dispatches through the type rather than the instance (`bool(x)`, `len(x)`,
`for _ in x`, `repr(x)`) - a hypothetical `if response:` would slip past this sentinel. It also
says nothing about code outside these eight methods (e.g. a hypothetical logger reading a
response through some other call site entirely). See `test_no_response_logging.py` for a
repository-wide backstop on that gap.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from arcadedb_driver_grpc.auth import async_interceptors, bearer_auth, sync_interceptors

# `_augment` (auth.py) reads `.method`, `.timeout`, `.metadata` and `.credentials` off
# `client_call_details`, plus `wait_for_ready`/`compression` via `getattr(..., default)` - a
# plain namespace with just the four required attributes is enough; the two optional ones
# default through `getattr` regardless.
_FAKE_CALL_DETAILS = SimpleNamespace(
    method="/com.arcadedb.grpc.ArcadeDbAdminService/Ping", timeout=None, metadata=(), credentials=None
)


class _AccessRecordingSentinel:
    """Stands in for a response (or a streaming call object). Reading ANY attribute off it
    records the name and raises `AttributeError` immediately - so an interceptor that starts
    inspecting its return value fails loudly, in the interceptor's own code, rather than merely
    tripping a downstream assertion.
    """

    def __getattribute__(self, name: str) -> object:
        object.__getattribute__(self, "_accessed").add(name)
        raise AttributeError(f"interceptor read {name!r} off the response sentinel")

    def __init__(self) -> None:
        object.__setattr__(self, "_accessed", set[str]())


def _accessed(sentinel: _AccessRecordingSentinel) -> set[str]:
    # Bypasses the sentinel's own `__getattribute__` override (which would otherwise record
    # and raise on this very read) by going straight to `object`'s implementation.
    return object.__getattribute__(sentinel, "_accessed")  # type: ignore[no-any-return]


_UNARY_METHODS = ("intercept_unary_unary", "intercept_unary_stream")
_STREAM_METHODS = ("intercept_stream_unary", "intercept_stream_stream")


@pytest.mark.parametrize("method_name", _UNARY_METHODS)
def test_sync_interceptor_never_reads_a_unary_response(method_name: str) -> None:
    interceptor = sync_interceptors(bearer_auth("t0ken"))[0]
    sentinel = _AccessRecordingSentinel()

    def continuation(details: Any, request: Any) -> _AccessRecordingSentinel:
        return sentinel

    result = getattr(interceptor, method_name)(continuation, _FAKE_CALL_DETAILS, "request")

    assert result is sentinel
    assert _accessed(sentinel) == set()


@pytest.mark.parametrize("method_name", _STREAM_METHODS)
def test_sync_interceptor_never_reads_a_streamed_response(method_name: str) -> None:
    interceptor = sync_interceptors(bearer_auth("t0ken"))[0]
    sentinel = _AccessRecordingSentinel()

    def continuation(details: Any, request_iterator: Any) -> _AccessRecordingSentinel:
        return sentinel

    result = getattr(interceptor, method_name)(continuation, _FAKE_CALL_DETAILS, iter(()))

    assert result is sentinel
    assert _accessed(sentinel) == set()


# `async_interceptors` returns FOUR separate objects, one per call shape (see auth.py's
# module-level comment on why a single combined class would silently drop three of them
# under `grpc.aio`'s interceptor bucketing) - so, unlike the sync case above, each shape's
# interceptor is a distinct object at a fixed index, not the same object called four ways.
_ASYNC_SHAPES = (
    (0, "intercept_unary_unary", "request"),
    (1, "intercept_unary_stream", "request"),
    (2, "intercept_stream_unary", "request_iterator"),
    (3, "intercept_stream_stream", "request_iterator"),
)


@pytest.mark.parametrize("index, method_name, request_kind", _ASYNC_SHAPES)
@pytest.mark.asyncio
async def test_async_interceptor_never_reads_a_response(index: int, method_name: str, request_kind: str) -> None:
    interceptor = async_interceptors(bearer_auth("t0ken"))[index]
    sentinel = _AccessRecordingSentinel()

    async def continuation(details: Any, request: Any) -> _AccessRecordingSentinel:
        return sentinel

    request_arg: Any = "request" if request_kind == "request" else iter(())
    result = await getattr(interceptor, method_name)(continuation, _FAKE_CALL_DETAILS, request_arg)

    assert result is sentinel
    assert _accessed(sentinel) == set()
