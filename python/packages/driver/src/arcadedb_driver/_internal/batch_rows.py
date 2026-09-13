"""Turning structured rows into ArcadeDB's GraphBatch ndjson line format.

This format was established against a live 26.10.1-SNAPSHOT server and reported upstream as
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

The whole payload is materialized as one string. The request body is streamed to the server
either way, so this costs a caller memory only for the payload they already hold; a caller whose
payload does not fit in memory needs a different design, and should be told that rather than be
handed a client that pretends otherwise.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
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


def serialize_rows(vertices: Iterable[VertexRow], edges: Iterable[EdgeRow]) -> str:
    """Serializes rows to the ndjson payload - vertices first, properties flattened."""
    out = []
    for vertex in vertices:
        control = {"@type": "vertex", "@class": vertex["type"]}
        if vertex.get("id") is not None:
            control["@id"] = vertex["id"]
        out.append(_line(control, vertex.get("properties")))
    for edge in edges:
        control = {"@type": "edge", "@class": edge["type"], "@from": edge["from_"], "@to": edge["to"]}
        out.append(_line(control, edge.get("properties")))
    return "".join(out)
