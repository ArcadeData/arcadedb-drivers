"""End-to-end tests for the `/ws` insert session against a real ArcadeDB server.

Requires Docker. Mirrors the server repository's `Issue7403RemoteInsertSessionIT`, which is the
Java client's own test: the caller commits after seeing the acknowledgements, rolls back after
seeing them, a session closed uncommitted is rolled back, a session joins the database's own HTTP
transaction (and that transaction's commit/rollback is what decides), joining needs a transaction
to join, and a chunk refused for its rows leaves the session usable under the same sequence number.
The server runs with `wsMaxInsertChunkRows` lowered to `WS_MAX_CHUNK_ROWS` (see `ws_server`).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator

import pytest
from arcadedb_driver import ArcadeDBDatabase, ArcadeDBServer, AsyncArcadeDBServer, InsertSessionError, basic_auth

from .conftest import ROOT_PASSWORD, WS_MAX_CHUNK_ROWS

_types = itertools.count(1)


@pytest.fixture
def server(ws_server: str, ws_database: str) -> Iterator[ArcadeDBServer]:
    with ArcadeDBServer(base_url=ws_server, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        yield srv


@pytest.fixture
def person(server: ArcadeDBServer, ws_database: str) -> str:
    """A fresh vertex type per test, so no test sees another's rows."""
    name = f"WsPerson{next(_types)}"
    server.db(ws_database).command(language="sql", command=f"CREATE VERTEX TYPE {name}")
    return name


def count(db: ArcadeDBDatabase, type_name: str) -> int:
    row = db.query(language="sql", command=f"SELECT count(*) AS n FROM {type_name}").result[0]
    return int(row["n"])


def people(*names: str) -> list[dict[str, str]]:
    return [{"name": n} for n in names]


def test_the_caller_commits_after_seeing_the_acknowledgements(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    seen: list[int] = []
    with db.insert_session(target_type=person, on_batch_ack=lambda ack: seen.append(ack["chunkSeq"])) as session:
        assert session.session_id
        assert session.transaction_mode == "per_stream"
        assert session.send_chunk(people("a", "b"))["inserted"] == 2
        assert session.send_chunk(people("c"))["inserted"] == 1
        assert seen == [1, 2]

        # Nothing is durable until the client says so.
        assert count(db, person) == 0

        committed = session.commit()
        assert committed["outcome"] == "commit"
        assert committed["summary"]["inserted"] == 3

    assert count(db, person) == 3


def test_the_caller_can_roll_back_after_seeing_the_acknowledgements(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    with db.insert_session(target_type=person) as session:
        assert session.send_chunk(people("a", "b"))["inserted"] == 2
        assert session.rollback()["outcome"] == "rollback"
    assert count(db, person) == 0


def test_closing_without_committing_rolls_the_session_back(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    with db.insert_session(target_type=person) as session:
        assert session.send_chunk(people("a"))["inserted"] == 1
    assert count(db, person) == 0


def test_a_session_joins_the_transaction_and_its_commit_decides(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    with db.transaction() as tx:
        with tx.insert_session(target_type=person, join_current_transaction=True) as session:
            assert session.transaction_mode == "none"
            assert session.external_transaction_id
            assert session.send_chunk(people("a", "b"))["inserted"] == 2
            committed = session.commit()
            assert committed["outcome"] == "detached"
            assert committed["summary"]["externalTransaction"] is True

        # Still nothing: the session committed nothing, it only stopped writing.
        assert count(db, person) == 0

    assert count(db, person) == 2


def test_the_transactions_rollback_undoes_what_the_joined_session_wrote(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)

    class Abort(Exception):
        pass

    with pytest.raises(Abort), db.transaction() as tx:
        with tx.insert_session(target_type=person, join_current_transaction=True) as session:
            assert session.send_chunk(people("a", "b"))["inserted"] == 2
            session.commit()
        raise Abort

    assert count(db, person) == 0


def test_joining_without_an_open_transaction_is_refused(server: ArcadeDBServer, ws_database: str) -> None:
    with pytest.raises(InsertSessionError, match="no open transaction"):
        server.db(ws_database).insert_session(join_current_transaction=True)


def test_a_refused_chunk_is_reported_and_the_session_carries_on(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    with db.insert_session(target_type=person) as session:
        too_many = people(*[str(i) for i in range(WS_MAX_CHUNK_ROWS + 1)])
        with pytest.raises(InsertSessionError, match=f"more than the {WS_MAX_CHUNK_ROWS}") as refused:
            session.send_chunk(too_many)
        assert refused.value.session_closed is False
        assert session.last_chunk_seq == 0, "a refused chunk must not consume a sequence number"

        # A row the server cannot apply, by contrast, is tallied rather than refused.
        ack = session.send_chunk([{"name": "a"}, {"@class": "NoSuchType"}])
        assert (ack["chunkSeq"], ack["inserted"], ack["failed"]) == (1, 1, 1)
        session.commit()

    assert count(db, person) == 1


def test_a_client_chosen_session_id_is_used_and_cannot_be_taken_twice(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    with db.insert_session(session_id=f"py-e2e-{person}", target_type=person) as first:
        assert first.session_id == f"py-e2e-{person}"
        with pytest.raises(InsertSessionError), db.insert_session(session_id=first.session_id):
            pass


@pytest.mark.asyncio
async def test_async_session_commits_after_the_acknowledgements(ws_server: str, ws_database: str, person: str) -> None:
    async with AsyncArcadeDBServer(base_url=ws_server, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        db = srv.db(ws_database)
        async with db.insert_session(target_type=person) as session:
            assert (await session.send_chunk(people("a", "b")))["inserted"] == 2
            assert (await session.commit())["outcome"] == "commit"
        env = await db.query(language="sql", command=f"SELECT count(*) AS n FROM {person}")
        assert int(env.result[0]["n"]) == 2


def test_a_whole_chunk_failure_is_acknowledged_and_replayed_under_the_same_sequence(
    server: ArcadeDBServer, ws_database: str, person: str
) -> None:
    db = server.db(ws_database)
    db.command(language="sql", command=f"CREATE PROPERTY {person}.name STRING")
    db.command(language="sql", command=f"CREATE INDEX ON {person} (name) UNIQUE")
    # A key already committed: the engine checks the unique index only when the chunk's own
    # transaction commits, which is what makes this a whole-chunk failure rather than a failed row
    # (the setup the server's Issue7471ChunkReplayTotalsIT uses).
    db.command(language="sql", command=f"INSERT INTO {person} SET name = 'taken'")
    seen: list[dict[str, object]] = []
    with db.insert_session(target_type=person, transaction_mode="per_batch", on_batch_ack=seen.append) as session:
        ack = session.send_chunk(people("taken"))
        assert ack["whole_chunk_failed"] is True, ack
        assert ack["failed"] == ack["received"] == 1
        assert session.last_chunk_seq == 0
        assert seen == [ack]

        replay = session.send_chunk(people("fresh"))
        assert replay["chunkSeq"] == 1
        assert replay["whole_chunk_failed"] is False
        assert replay["inserted"] == 1
        session.commit()

    assert count(db, person) == 2
