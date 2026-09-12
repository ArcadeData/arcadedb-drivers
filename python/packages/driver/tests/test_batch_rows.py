from __future__ import annotations

import json
from typing import Any

from arcadedb_driver._internal.batch_rows import serialize_rows


def _lines(payload: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in payload.split("\n") if line]


def test_properties_are_flattened_never_nested() -> None:
    # The whole point of the structured row type. The server ACCEPTS a nested
    # `properties` object and stores a property literally called "properties",
    # answering 200 with correct counters - silent data corruption. See the spec's
    # section 3 and ArcadeData/arcadedb#7570.
    (row,) = _lines(serialize_rows([{"type": "Person", "id": "p1", "properties": {"name": "Alice"}}], []))
    assert row == {"@type": "vertex", "@class": "Person", "@id": "p1", "name": "Alice"}
    assert "properties" not in row


def test_every_vertex_precedes_every_edge() -> None:
    # Not cosmetic: the server resolves an edge's @from/@to only against temp ids
    # declared EARLIER in the same payload, and answers 400 otherwise - possibly
    # after earlier chunks have already committed.
    rows = _lines(
        serialize_rows(
            [{"type": "Person", "id": "a"}, {"type": "Person", "id": "b"}],
            [{"type": "Knows", "from_": "a", "to": "b"}],
        )
    )
    assert [row["@type"] for row in rows] == ["vertex", "vertex", "edge"]


def test_id_is_omitted_when_absent() -> None:
    (row,) = _lines(serialize_rows([{"type": "Person", "properties": {"name": "Anon"}}], []))
    assert row == {"@type": "vertex", "@class": "Person", "name": "Anon"}


def test_an_explicit_none_id_is_treated_as_absent() -> None:
    # Sibling parity: `internal/batch-rows.ts` tests `v.id !== undefined`, so a vertex spelled
    # `{ id: undefined }` there never emits `@id`. `VertexRow` forbids `None` for `id`, so only an
    # unchecked caller reaches this, but `{"id": None}` must still behave the same way here rather
    # than emit `"@id": null` - this repository treats behavioural divergence between the two
    # clients as a defect in its own right, even when only one side is reachable through the type.
    (row,) = _lines(serialize_rows([{"type": "Person", "id": None, "properties": {"name": "Anon"}}], []))  # type: ignore[typeddict-item]
    assert row == {"@type": "vertex", "@class": "Person", "name": "Anon"}


def test_edge_endpoints_and_properties() -> None:
    (row,) = _lines(serialize_rows([], [{"type": "Knows", "from_": "a", "to": "#1:7", "properties": {"since": 2020}}]))
    assert row == {"@type": "edge", "@class": "Knows", "@from": "a", "@to": "#1:7", "since": 2020}


def test_every_line_is_newline_terminated() -> None:
    # A body whose final line has no terminator is a body that ends before its
    # announced length: the server answers 408, never a 200 with a short count.
    payload = serialize_rows([{"type": "Person"}], [{"type": "Knows", "from_": "a", "to": "b"}])
    assert payload.endswith("\n")
    assert len([line for line in payload.split("\n") if line]) == 2


def test_no_rows_is_the_empty_payload() -> None:
    assert serialize_rows([], []) == ""


def test_a_property_named_like_a_control_key_passes_through() -> None:
    # Properties live in their own dict in our type, so a property called "type"
    # or "from" cannot collide with a control field (spec D2).
    (row,) = _lines(serialize_rows([{"type": "Person", "properties": {"type": "civilian", "from": "Rome"}}], []))
    assert row == {"@type": "vertex", "@class": "Person", "type": "civilian", "from": "Rome"}
