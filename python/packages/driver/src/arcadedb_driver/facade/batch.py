"""The `batch_load` / `batch_load_stream` pair: `POST /api/v1/batch/{database}`, ArcadeDB's
bulk graph-load endpoint.

HAND-WRITTEN, and unlike `facade/stream.py`'s `query_stream`/`command_stream` there is no
generated request model to ride even for the buffered path: `openapi-python-client` cannot model
this endpoint's body at all - the contract declares it `{"type": "string"}` for jsonl/ndjson/csv
alike, not a JSON schema - so it prints a warning, skips the operation entirely, and exits 0.
`_generated/api/batch/__init__.py` is an empty stub, and `POST /api/v1/batch/{database}` is one of
the four entries `scripts/check_codegen_skips.py` pins in `EXPECTED_SKIPS`. `facade/timeseries.py`'s
hand-written `write` is the closer relative: both issue a raw request through the generated
`Client`'s own pooled `httpx.Client`/`httpx.AsyncClient`, so auth headers, timeout and connection
pooling still apply, and both return `dict[str, Any]` rather than a generated model, because there
is no generated model to return here at all.

Two gaps in the contract's declared shapes carry over from `@arcadedb/driver`'s `facade/batch.ts`,
so the two clients tell the same story even though only the TypeScript side has a generated type
to widen (there is nothing to widen here - this module returns parsed JSON either way):

- **`idMappingStreamed`.** The buffered response (`batch_load`) is the contract's declared
  `BatchResponse` shape: `idMapping`, `idMappingOmitted`, `idMappingSize`. A STREAMED load's
  `summary` event additionally carries `idMappingStreamed: true` - a field no schema declares,
  reported upstream on ArcadeData/arcadedb#7570. It is a genuinely different condition from
  `idMappingOmitted`: *omitted* means too large to return; *streamed* means already delivered,
  piecemeal, in the `progress` events that came before the summary. Progress events are yielded
  exactly as received and never merged - accumulating `idMapping` fragments across events would
  reintroduce, client-side, the memory cost streaming a large load exists to avoid (D5; see
  `test_batch_load_stream_does_not_merge_id_mapping_fragments` in `test_batch.py`).
- **An in-band error's `error`/`exception` fields.** The contract's `NdJsonBatchEvent.error`
  object declares only `commitIndex`, `status` and `statusMapped`, but the server also sends
  `error` (the message) and `exception` - the same two fields the BUFFERED encoding's
  `BatchError` declares. `_raise_on_error_event` reads both off the raw dict.

**D6: the two error channels collapse into one `ArcadeDBError`.** A load that fails BEFORE the
first line is written to the response answers with a real HTTP status and the buffered error
body, because the status line has not been sent yet. A load that fails AFTER the first progress
line cannot do that - the 200 status line is already on the wire and cannot be taken back - so the
failure arrives in band instead, carrying the status the buffered encoding would have used.
`_raise_on_error_event` raises `ArcadeDBError` for both channels, so a caller's `for` loop fails
the same way regardless of which one produced the failure; only the moment of failure differs, and
that is not something a caller can act on. `statusMapped: false` marks `status` as an
unclassified 500 fallback rather than the status the buffered encoding would have chosen - the
contract says to key on `exception` in that case, so the raised error's `detail` says so. Any
event already yielded before the error stays delivered to the caller; the exception is raised from
the iterator at the point the `error` event arrives, not before.

Every vertex is serialized before any edge (`serialize_rows`, in `_internal/batch_rows.py`), and a
batch is not atomic - the server commits every `options["commitEvery"]` records, so a failure
partway through can leave earlier chunks durably committed. Because temporary ids are not keys,
retrying a failed call duplicates whatever already landed rather than resuming cleanly; this
module does not track or dedupe that on a caller's behalf.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator, Iterable
from typing import Any
from urllib.parse import quote

from typing_extensions import NotRequired, TypedDict

from .._generated.client import Client
from .._internal.batch_rows import EdgeRow, VertexRow, serialize_rows
from .._internal.ndjson import aiter_ndjson_lines, araise_for_status, iter_ndjson_lines, raise_for_status
from ..errors import ArcadeDBError

__all__ = [
    "BatchOptions",
    "EdgeRow",
    "VertexRow",
    "abatch_load",
    "abatch_load_stream",
    "batch_load",
    "batch_load_stream",
]


class BatchOptions(TypedDict):
    """The 17 tuning parameters `POST /api/v1/batch/{database}` accepts as query parameters,
    named exactly as the contract names them.

    `idMapping` and `refMode` are left as plain `str` rather than narrowed to the contract's
    declared `"auto"|"true"|"false"` / `"id"|"ordinal"` literals, matching
    `@arcadedb/driver`'s `BatchOptions`: this repository treats the two clients diverging as a
    defect in its own right, so narrowing only one of them would trade a weak-typing issue for a
    sibling-divergence one.
    """

    batchSize: NotRequired[int]
    lightEdges: NotRequired[bool]
    wal: NotRequired[bool]
    parallelFlush: NotRequired[bool]
    preAllocateEdgeChunks: NotRequired[bool]
    edgeListInitialSize: NotRequired[int]
    bidirectional: NotRequired[bool]
    commitEvery: NotRequired[int]
    expectedEdgeCount: NotRequired[int]
    commitRetries: NotRequired[int]
    commitRetryDelayMs: NotRequired[int]
    vertexBatchSize: NotRequired[int]
    expectedVertexCount: NotRequired[int]
    expectedRecords: NotRequired[int]
    ordinalBase: NotRequired[int]
    idMapping: NotRequired[str]
    refMode: NotRequired[str]


def _batch_url(database: str) -> str:
    return f"/api/v1/batch/{quote(database, safe='')}"


def _params(options: BatchOptions | None) -> dict[str, Any] | None:
    """Builds the query parameters from `options`, or `None` when there are none.

    Not "sends an empty value": an absent option must leave the parameter off the URL entirely,
    so the server applies its own default rather than parsing `""`. A `TypedDict` with
    `NotRequired` fields already makes this the natural behaviour - an absent key simply never
    appears in `options.items()` - so there is nothing to filter out explicitly.
    """
    return dict(options) if options else None


def _raise_on_error_event(event: dict[str, Any]) -> dict[str, Any]:
    """Raises `ArcadeDBError` for an in-band `error` event instead of returning it - see the
    module docstring's "D6" section for why this is the same failure as a non-2xx response, and
    why `statusMapped: false` means the raised error's `detail` should point at `exception`
    instead of trusting `status`."""
    error = event.get("error")
    if error is None:
        return event
    status = error.get("status")
    body: dict[str, Any] = {"error": error.get("error") or "the batch load reported an error"}
    if error.get("exception") is not None:
        body["exception"] = error["exception"]
    if error.get("statusMapped") is False:
        body["detail"] = "status is an unclassified fallback; key on exception"
    raise ArcadeDBError(status if status is not None else 500, body)


def batch_load(
    client: Client,
    database: str,
    *,
    vertices: Iterable[VertexRow] = (),
    edges: Iterable[EdgeRow] = (),
    options: BatchOptions | None = None,
) -> dict[str, Any]:
    """Bulk-loads vertices and edges in one call to `POST /api/v1/batch/{database}`, buffering
    the whole response before returning.

    Returns the parsed JSON body unaltered rather than a generated model - there is no generated
    model for this endpoint at all (see the module docstring). The body is the contract's
    `BatchResponse` shape: `verticesCreated`, `edgesCreated`, `idMapping`, `idMappingOmitted`,
    `idMappingSize`, `partialCommit`, and so on.

    `vertices` are always serialized before `edges`, regardless of the order a caller passes them
    in - the server resolves an edge's `from`/`to` only against ids declared earlier in the SAME
    payload, and `serialize_rows` enforces that ordering unconditionally.

    A load is NOT atomic: the server commits every `options["commitEvery"]` records, so a failure
    partway through leaves earlier chunks durably committed - an `ArcadeDBError` raised from a
    failed load still corresponds to real, already-durable data. Because temporary ids are not
    keys, retrying the whole payload after such a failure duplicates whatever already committed
    rather than resuming cleanly. Use `batch_load_stream` when the caller needs to see how far a
    load got before it failed.
    """
    raw = client.get_httpx_client().post(
        _batch_url(database),
        content=serialize_rows(vertices, edges).encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        params=_params(options),
    )
    raise_for_status(raw)
    body: dict[str, Any] = raw.json()
    return body


def batch_load_stream(
    client: Client,
    database: str,
    *,
    vertices: Iterable[VertexRow] = (),
    edges: Iterable[EdgeRow] = (),
    options: BatchOptions | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Streams the same bulk load as `batch_load`, but as `application/x-ndjson`: a `progress`
    event at every vertex commit and every `options["commitEvery"]` edges, then exactly one
    `summary` event carrying the same object the buffered call would otherwise have returned
    (plus `idMappingStreamed` - see the module docstring for what that field means and why it is
    not in the contract).

    An in-band `error` event raises `ArcadeDBError` instead of being yielded - see the module
    docstring's "D6" section for why the two ways a load can fail (before vs. after the first
    acknowledgement) both end up on this one throwing path. Any event already yielded before the
    error stays delivered; the exception is raised from the iterator at the point the `error`
    event arrives, so a caller who was already told about earlier progress does not lose that
    information along with the failure - a partial commit is durable, and those progress counts
    are how a caller learns what may have landed.

    A `progress` event's `idMapping` is only the fragment that chunk resolved - it is never
    merged across events (D5), so a caller that needs the whole mapping must concatenate it
    themselves as they receive it.
    """
    with client.get_httpx_client().stream(
        "POST",
        _batch_url(database),
        content=serialize_rows(vertices, edges).encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson", "Accept": "application/x-ndjson"},
        params=_params(options),
    ) as response:
        raise_for_status(response)
        for line in iter_ndjson_lines(response.iter_text()):
            if not line.strip():
                continue
            yield _raise_on_error_event(json.loads(line))


async def abatch_load(
    client: Client,
    database: str,
    *,
    vertices: Iterable[VertexRow] = (),
    edges: Iterable[EdgeRow] = (),
    options: BatchOptions | None = None,
) -> dict[str, Any]:
    """Bulk-loads vertices and edges in one call to `POST /api/v1/batch/{database}`, buffering
    the whole response before returning.

    Returns the parsed JSON body unaltered rather than a generated model - there is no generated
    model for this endpoint at all (see the module docstring). The body is the contract's
    `BatchResponse` shape: `verticesCreated`, `edgesCreated`, `idMapping`, `idMappingOmitted`,
    `idMappingSize`, `partialCommit`, and so on.

    `vertices` are always serialized before `edges`, regardless of the order a caller passes them
    in - the server resolves an edge's `from`/`to` only against ids declared earlier in the SAME
    payload, and `serialize_rows` enforces that ordering unconditionally.

    A load is NOT atomic: the server commits every `options["commitEvery"]` records, so a failure
    partway through leaves earlier chunks durably committed - an `ArcadeDBError` raised from a
    failed load still corresponds to real, already-durable data. Because temporary ids are not
    keys, retrying the whole payload after such a failure duplicates whatever already committed
    rather than resuming cleanly. Use `batch_load_stream` when the caller needs to see how far a
    load got before it failed.
    """
    raw = await client.get_async_httpx_client().post(
        _batch_url(database),
        content=serialize_rows(vertices, edges).encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
        params=_params(options),
    )
    await araise_for_status(raw)
    body: dict[str, Any] = raw.json()
    return body


async def abatch_load_stream(
    client: Client,
    database: str,
    *,
    vertices: Iterable[VertexRow] = (),
    edges: Iterable[EdgeRow] = (),
    options: BatchOptions | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Streams the same bulk load as `batch_load`, but as `application/x-ndjson`: a `progress`
    event at every vertex commit and every `options["commitEvery"]` edges, then exactly one
    `summary` event carrying the same object the buffered call would otherwise have returned
    (plus `idMappingStreamed` - see the module docstring for what that field means and why it is
    not in the contract).

    An in-band `error` event raises `ArcadeDBError` instead of being yielded - see the module
    docstring's "D6" section for why the two ways a load can fail (before vs. after the first
    acknowledgement) both end up on this one throwing path. Any event already yielded before the
    error stays delivered; the exception is raised from the iterator at the point the `error`
    event arrives, so a caller who was already told about earlier progress does not lose that
    information along with the failure - a partial commit is durable, and those progress counts
    are how a caller learns what may have landed.

    A `progress` event's `idMapping` is only the fragment that chunk resolved - it is never
    merged across events (D5), so a caller that needs the whole mapping must concatenate it
    themselves as they receive it.
    """
    async with client.get_async_httpx_client().stream(
        "POST",
        _batch_url(database),
        content=serialize_rows(vertices, edges).encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson", "Accept": "application/x-ndjson"},
        params=_params(options),
    ) as response:
        await araise_for_status(response)
        async for line in aiter_ndjson_lines(response.aiter_text()):
            if not line.strip():
                continue
            yield _raise_on_error_event(json.loads(line))
