"""End-to-end tests for `batch_load` / `batch_load_stream` against a real ArcadeDB server.

Requires Docker. This is the only test in the branch that proves the ndjson wire format
`_internal/batch_rows.py`'s `serialize_rows` produces against the server that defines it - every
other batch test in the suite runs against a mock.
"""

from __future__ import annotations

import pytest
from arcadedb_driver import ArcadeDBServer, AsyncArcadeDBServer, basic_auth

from .conftest import ROOT_PASSWORD

BATCH_TYPE = "Person"
BATCH_EDGE_TYPE = "Knows"


@pytest.fixture(scope="module")
def batch_schema(base_url: str, database: str) -> str:
    """Creates the vertex/edge types a batch load resolves against, over HTTP.

    The batch endpoint has no DDL of its own - exactly the reason `conftest.py`'s
    `grpc_timeseries_type` fixture creates its type over HTTP - so `Person`/`Knows` and the
    `name` property a later test reads back must exist before any batch load reaches the server.
    Module-scoped so it runs once no matter how many tests in this file need it, reusing the
    session-scoped `database` fixture's database rather than creating a second one.
    """
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(database)
        db.command(language="sql", command=f"CREATE VERTEX TYPE {BATCH_TYPE} IF NOT EXISTS")
        db.command(language="sql", command=f"CREATE PROPERTY {BATCH_TYPE}.name IF NOT EXISTS STRING")
        db.command(language="sql", command=f"CREATE EDGE TYPE {BATCH_EDGE_TYPE} IF NOT EXISTS")
    return database


def test_batch_load_creates_vertices_and_edges(base_url: str, batch_schema: str) -> None:
    """Loads two vertices and one edge, asserting the counters and that every declared temp id
    resolved to a real RID in the returned idMapping."""
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(batch_schema)

        summary = db.batch_load(
            vertices=[
                {"type": BATCH_TYPE, "id": "a", "properties": {"name": "Ann"}},
                {"type": BATCH_TYPE, "id": "b", "properties": {"name": "Ben"}},
            ],
            edges=[{"type": BATCH_EDGE_TYPE, "from_": "a", "to": "b", "properties": {"since": 2020}}],
        )

        assert summary["verticesCreated"] == 2
        assert summary["edgesCreated"] == 1
        id_mapping = summary.get("idMapping") or {}
        assert {"a", "b"} <= set(id_mapping.keys())


def test_properties_are_stored_as_real_fields(base_url: str, batch_schema: str) -> None:
    """The regression guard for the corruption of the spec's section 3. If a refactor ever nests
    properties again, the load still answers 200 with correct counters - only a query for the
    property by name notices. This is the ONLY test in the suite that would."""
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(batch_schema)

        db.batch_load(vertices=[{"type": BATCH_TYPE, "id": "c", "properties": {"name": "Cat"}}])

        env = db.query(language="sql", command=f"SELECT FROM {BATCH_TYPE} WHERE name = 'Cat'")
        assert len(env.result) == 1
        assert env.result[0]["name"] == "Cat"


def test_batch_load_stream_reports_progress_before_its_summary(base_url: str, batch_schema: str) -> None:
    """With commitEvery=1, at least one progress event arrives before exactly one summary."""
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(batch_schema)

        events = list(
            db.batch_load_stream(
                vertices=[
                    {"type": BATCH_TYPE, "id": "d", "properties": {"name": "Dan"}},
                    {"type": BATCH_TYPE, "id": "e", "properties": {"name": "Eve"}},
                ],
                edges=[{"type": BATCH_EDGE_TYPE, "from_": "d", "to": "e"}],
                options={"commitEvery": 1},
            )
        )

    progress_events = [e for e in events if "progress" in e]
    summary_events = [e for e in events if "summary" in e]

    assert len(progress_events) > 0
    assert len(summary_events) == 1
    # The summary must be the LAST event, i.e. every progress event precedes it.
    assert "summary" in events[-1]

    # The streamed shape from the Amendment: idMappingStreamed: true with idMappingSize, NOT the
    # buffered idMapping map.
    assert summary_events[0]["summary"]["idMappingStreamed"] is True
    assert isinstance(summary_events[0]["summary"]["idMappingSize"], int)
    assert "idMapping" not in summary_events[0]["summary"]


@pytest.mark.asyncio
async def test_async_batch_load_creates_vertices_and_edges(base_url: str, batch_schema: str) -> None:
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(batch_schema)

        summary = await db.batch_load(
            vertices=[
                {"type": BATCH_TYPE, "id": "f", "properties": {"name": "Fay"}},
                {"type": BATCH_TYPE, "id": "g", "properties": {"name": "Gia"}},
            ],
            edges=[{"type": BATCH_EDGE_TYPE, "from_": "f", "to": "g", "properties": {"since": 2021}}],
        )

        assert summary["verticesCreated"] == 2
        assert summary["edgesCreated"] == 1
        id_mapping = summary.get("idMapping") or {}
        assert {"f", "g"} <= set(id_mapping.keys())


@pytest.mark.asyncio
async def test_async_properties_are_stored_as_real_fields(base_url: str, batch_schema: str) -> None:
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(batch_schema)

        await db.batch_load(vertices=[{"type": BATCH_TYPE, "id": "h", "properties": {"name": "Hal"}}])

        env = await db.query(language="sql", command=f"SELECT FROM {BATCH_TYPE} WHERE name = 'Hal'")
        assert len(env.result) == 1
        assert env.result[0]["name"] == "Hal"


@pytest.mark.asyncio
async def test_async_batch_load_stream_reports_progress_before_its_summary(base_url: str, batch_schema: str) -> None:
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(batch_schema)

        events = [
            event
            async for event in db.batch_load_stream(
                vertices=[
                    {"type": BATCH_TYPE, "id": "i", "properties": {"name": "Ida"}},
                    {"type": BATCH_TYPE, "id": "j", "properties": {"name": "Jon"}},
                ],
                edges=[{"type": BATCH_EDGE_TYPE, "from_": "i", "to": "j"}],
                options={"commitEvery": 1},
            )
        ]

    progress_events = [e for e in events if "progress" in e]
    summary_events = [e for e in events if "summary" in e]

    assert len(progress_events) > 0
    assert len(summary_events) == 1
    assert "summary" in events[-1]
    assert summary_events[0]["summary"]["idMappingStreamed"] is True
    assert isinstance(summary_events[0]["summary"]["idMappingSize"], int)
    assert "idMapping" not in summary_events[0]["summary"]
