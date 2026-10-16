"""List and terminate running work, and `progress`, against a real server (issue #124). Each
status and the 409 pinned here were measured, not read off the contract: the contract does not
describe these answers at all."""

import asyncio
import itertools
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from arcadedb_driver import (
    ArcadeDBError,
    ArcadeDBServer,
    AsyncArcadeDBServer,
    RunningQuery,
    basic_auth,
    is_query_terminated,
)

from .conftest import ROOT_PASSWORD

# Runs until it is terminated. SQL SLEEP would not do: it notices a terminate only when it ends,
# so it is answered "terminating" rather than "terminated".
LONG_LOOP = "LET i = 0; WHILE ($i < 1000000000) { LET i = $i + 1; } RETURN $i"

_counter = itertools.count()


def unique(prefix: str) -> str:
    return f"{prefix}{next(_counter)}{uuid.uuid4().hex[:6]}"


@pytest.fixture
def srv(base_url: str) -> Iterator[ArcadeDBServer]:
    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as server:
        yield server


@pytest.fixture
def fresh_db(srv: ArcadeDBServer) -> Iterator[str]:
    name = unique("pyrunning")
    srv.create_database(name)
    yield name
    srv.drop_database(name)


def wait_for_query(srv: ArcadeDBServer, **filters: str) -> RunningQuery:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        found = srv.list_queries(**filters)
        if found:
            return found[0]
        time.sleep(0.1)
    raise AssertionError(f"no running query matched {filters}")


def test_list_and_terminate_queries_by_tag(srv: ArcadeDBServer, fresh_db: str) -> None:
    tag = unique("py running ")  # a space, to cross the rest-of-line parse
    outcome: list[BaseException | None] = []

    def run() -> None:
        try:
            srv.db(fresh_db).command(language="sqlscript", command=LONG_LOOP, query_tag=tag)
            outcome.append(None)
        except BaseException as e:  # handed back to the test thread
            outcome.append(e)

    worker = threading.Thread(target=run)
    worker.start()
    query = wait_for_query(srv, database=fresh_db, tag=tag)
    assert (query.tag, query.database, query.language, query.text, query.session_id) == (
        tag,
        fresh_db,
        "sqlscript",
        LONG_LOOP,
        None,
    )

    results = srv.terminate_queries_by_tag(tag, wait=timedelta(seconds=5))
    assert [(r.id, r.status) for r in results] == [(query.id, "terminated")]

    worker.join(15)
    assert not worker.is_alive()
    (error,) = outcome
    assert error is not None and is_query_terminated(error)
    assert isinstance(error, ArcadeDBError) and (error.status, error.error) == (409, "Query terminated")

    assert srv.list_queries(tag=tag) == []
    assert srv.terminate_query(query.id).status == "not found"


def test_terminate_query_inside_a_transaction(srv: ArcadeDBServer, fresh_db: str) -> None:
    tag = unique("py-tx-")
    outcome: list[BaseException | None] = []
    with pytest.raises(ArcadeDBError) as caught, srv.db(fresh_db).transaction() as tx:

        def run() -> None:
            try:
                tx.command(language="sqlscript", command=LONG_LOOP, query_tag=tag)
                outcome.append(None)
            except BaseException as e:  # handed back to the test thread
                outcome.append(e)

        worker = threading.Thread(target=run)
        worker.start()
        query = wait_for_query(srv, tag=tag)
        assert query.session_id is not None

        (open_tx,) = [t for t in srv.list_transactions() if t.id == query.session_id]
        assert open_tx.busy and open_tx.database == fresh_db and query.id in open_tx.running_queries

        result = srv.terminate_query(query.id, wait=timedelta(seconds=5))
        # A script is a command, so terminating it ends the session it ran in.
        assert (result.status, result.session_id, result.session_open) == ("terminated", query.session_id, False)
        worker.join(15)
        (error,) = outcome
        assert error is not None
        raise error
    assert is_query_terminated(caught.value)


def test_terminate_transaction_is_not_seen_at_commit(srv: ArcadeDBServer, fresh_db: str) -> None:
    """The server answers a commit naming a session it no longer has with 204, like a real
    commit, so the block exits cleanly although its insert was rolled back. The README and the
    `terminate_transaction` docstring warn about it; if this starts failing, update both."""
    db = srv.db(fresh_db)
    db.command(language="sql", command="CREATE DOCUMENT TYPE Doc")
    with db.transaction() as tx:
        tx.command(language="sql", command="INSERT INTO Doc SET x = 1")
        (open_tx,) = [t for t in srv.list_transactions() if t.database == fresh_db]
        assert srv.terminate_transaction(open_tx.id).status == "terminated"
        with pytest.raises(ArcadeDBError) as caught:
            tx.query(language="sql", command="SELECT 1")
        assert caught.value.status == 404
    assert db.query(language="sql", command="SELECT count(*) AS n FROM Doc").result == [{"n": 0}]
    assert srv.terminate_transaction(open_tx.id).status == "not found"


def test_progress_with_nothing_running(srv: ArcadeDBServer, fresh_db: str) -> None:
    assert srv.db(fresh_db).progress().result == []


@pytest.mark.asyncio
async def test_async_list_and_terminate_by_tag(base_url: str, fresh_db: str) -> None:
    tag = unique("py-async-")
    async with AsyncArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        task = asyncio.create_task(srv.db(fresh_db).command(language="sqlscript", command=LONG_LOOP, query_tag=tag))
        deadline = time.monotonic() + 15
        while not await srv.list_queries(tag=tag):
            assert time.monotonic() < deadline, "the tagged query never showed up"
            await asyncio.sleep(0.1)
        results = await srv.terminate_queries_by_tag(tag, wait=timedelta(seconds=5))
        assert [r.status for r in results] == ["terminated"]
        with pytest.raises(ArcadeDBError) as caught:
            await task
        assert is_query_terminated(caught.value)
        assert (await srv.db(fresh_db).progress()).result == []
