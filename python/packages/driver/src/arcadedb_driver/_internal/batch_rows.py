"""Turning structured rows into ArcadeDB's GraphBatch ndjson line format.

This format was established against a live 26.10.1 server and reported upstream as
ArcadeData/arcadedb#7570, because no contract described it. The contract now DOES describe it -
the jsonl and ndjson bodies are `BatchLine`, a discriminated union over `BatchVertexLine` and
`BatchEdgeLine`, and it matches what this module already emitted, field for field. That does not
make this module redundant: `BatchLine` describes ONE LINE, not the body. The contract says so
outright - "The JSON schema below describes ONE LINE: the body is a sequence of them" - so a
generator still cannot produce a usable call from it, and `openapi-python-client` still skips the
operation. `text/csv` remains a prose description with no schema at all::

    {"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}
    {"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}

Two properties of `serialize_rows` are load-bearing rather than stylistic:

1. **Properties are flattened beside the control keys, never nested.** The gRPC sibling
   `GraphBatchRecord` has a `properties` map field, so nesting is the natural guess - and the
   server ACCEPTS it, answers 200 with correct counters, and stores a property literally named
   `properties` holding the map. Nothing fails until someone queries for a field that is not
   there. Taking `properties` as its own dict in the row type and flattening it here means a
   caller cannot produce that payload.
2. **Every vertex is emitted before any edge.** The server resolves an edge's `@from`/`@to`
   against temp ids declared earlier in the SAME payload only, and answers 400 otherwise. Since
   a batch is not atomic, that 400 can arrive after earlier chunks have durably committed, and
   retrying duplicates them. Vertices and edges arrive as separate arguments precisely so the
   wrong order cannot be expressed.

`serialize_rows` materializes the whole payload as one string, and the default `vertices=`/`edges=`
path of `batch_load` sends that as one body with a `Content-Length`. A payload that does not fit in
memory has a second way in: `iter_rows` yields the same lines one at a time, and `iter_body` /
`aiter_body` (used by the `lines=` argument of the batch calls) pack any iterable of lines into
bounded chunks, so the request body is generated while it is sent and is never held whole.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Iterator
from typing import Any

from typing_extensions import NotRequired, TypedDict


class VertexRow(TypedDict):
    """A vertex to create."""

    type: str
    """The vertex type name, e.g. `"Person"`. Sent as `@class`."""
    id: NotRequired[str]
    """Optional temporary id, referenced by an edge's `from`/`to` in the same call and returned
    in the summary's `idMapping`. Vertices without one are counted in `verticesWithoutId`."""
    properties: NotRequired[dict[str, Any]]


class EdgeRow(TypedDict):
    """An edge to create, referencing vertices by temporary id or by RID."""

    type: str
    """The edge type name, e.g. `"Knows"`. Sent as `@class`."""
    from_: str
    """Source: a temp id declared by a vertex in this same call, or a literal
    `#bucket:position` RID. Spelled with a trailing underscore because `from` is a Python
    keyword and cannot be a TypedDict key in class syntax, while the wire name is `@from` and
    the TypeScript twin spells this field `from`. Same asymmetry as `ArcadeDBError.help_` in
    `errors.py`, and for the same reason - one explanation to point at instead of two
    coincidences."""
    to: str
    """Target: same rules as `from_`."""
    properties: NotRequired[dict[str, Any]]


def _line(control: dict[str, str], properties: dict[str, Any] | None) -> str:
    return json.dumps({**control, **(properties or {})}) + "\n"


def _row_lines(vertices: Iterable[VertexRow], edges: Iterable[EdgeRow]) -> Iterator[str]:
    for vertex in vertices:
        control = {"@type": "vertex", "@class": vertex["type"]}
        if vertex.get("id") is not None:
            control["@id"] = vertex["id"]
        yield _line(control, vertex.get("properties"))
    for edge in edges:
        control = {"@type": "edge", "@class": edge["type"], "@from": edge["from_"], "@to": edge["to"]}
        yield _line(control, edge.get("properties"))


def serialize_rows(vertices: Iterable[VertexRow], edges: Iterable[EdgeRow]) -> str:
    """Serializes rows to the ndjson payload - vertices first, properties flattened."""
    return "".join(_row_lines(vertices, edges))


def iter_rows(vertices: Iterable[VertexRow], edges: Iterable[EdgeRow]) -> Iterator[bytes]:
    """Yields the same ndjson lines `serialize_rows` joins, one UTF-8 encoded line at a time, so
    the payload is never built whole: every vertex first, properties flattened, and each row is
    pulled from `vertices`/`edges` only when the next line is asked for. Pass the result as the
    `lines=` argument of a batch call to stream rows from a generator."""
    for line in _row_lines(vertices, edges):
        yield line.encode("utf-8")


CHUNK_BYTES = 64 * 1024
"""A streamed body is sent in chunks of about this many bytes (a chunk ends at the first line
that reaches it), so one call to the transport carries many lines rather than one."""


def _line_bytes(line: object) -> bytes:
    """One line as UTF-8 bytes ending in a single newline, or `b""` for an empty line."""
    if isinstance(line, str):
        data = line.encode("utf-8")
    elif isinstance(line, (bytes, bytearray, memoryview)):
        data = bytes(line)
    else:
        raise TypeError(f"a line must be str or bytes, not {type(line).__name__}")
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data


def iter_body(lines: Iterable[str | bytes]) -> Iterator[bytes]:
    """Packs ndjson lines into chunks of about `CHUNK_BYTES`, pulling `lines` lazily: no line is
    taken before the transport asks for the chunk that holds it, and at most one chunk is held
    at a time. A line without a trailing newline gets one; an empty line is dropped."""
    buffer = bytearray()
    for line in lines:
        buffer += _line_bytes(line)
        if len(buffer) >= CHUNK_BYTES:
            yield bytes(buffer)
            buffer.clear()
    if buffer:
        yield bytes(buffer)


async def aiter_body(lines: Iterable[str | bytes] | AsyncIterable[str | bytes]) -> AsyncIterator[bytes]:
    """The async twin of `iter_body`. A plain iterable (a list, a file object) is read on the
    event loop thread, line by line, which suits a generator or an in-memory source; an
    `AsyncIterable` is awaited between lines."""
    buffer = bytearray()
    if isinstance(lines, AsyncIterable):
        async for line in lines:
            buffer += _line_bytes(line)
            if len(buffer) >= CHUNK_BYTES:
                yield bytes(buffer)
                buffer.clear()
    else:
        for line in lines:
            buffer += _line_bytes(line)
            if len(buffer) >= CHUNK_BYTES:
                yield bytes(buffer)
                buffer.clear()
    if buffer:
        yield bytes(buffer)
