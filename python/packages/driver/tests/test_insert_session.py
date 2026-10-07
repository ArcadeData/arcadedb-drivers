"""Offline tests for the `/ws` insert session, against an in-process fake of the server's frames.

The fake (`FakeInsertServer`) is a small `websockets` server on a background thread that speaks the
frame shapes `WebSocketInsertProtocol` documents - `start`/`started`, `chunk`/`batchAck`,
`commit`|`rollback`/`committed`, `error` - closely enough to exercise the client's rules: it does
NOT claim to be the server. The real thing is covered by `e2e/test_insert_session.py`.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from arcadedb_driver import (
    ArcadeDBDatabase,
    ArcadeDBServer,
    AsyncArcadeDBDatabase,
    AsyncArcadeDBServer,
    InsertSessionError,
    basic_auth,
)
from websockets.asyncio.server import ServerConnection, serve

MAX_ROWS = 4


class FakeInsertServer:
    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        self.sessions: dict[str, dict[str, Any]] = {}
        self.counter = 0
        #: Push an unsolicited idle-sweep `error` before answering the next frame.
        self.expire_before_next_answer = False
        #: Close with 1009 instead of answering a chunk.
        self.close_1009_on_chunk = False
        #: Answer the next chunk with this error frame instead of an ack.
        self.error_on_next_chunk: dict[str, Any] | None = None
        #: Never answer a chunk.
        self.silent_on_chunk = False
        self.port = 0
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop: asyncio.Future[None] | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        assert self._ready.wait(10)

    def stop(self) -> None:
        assert self._stop is not None
        self._loop.call_soon_threadsafe(self._stop.set_result, None)
        self._thread.join(10)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self) -> None:
        self._stop = self._loop.create_future()
        async with serve(self._handle, "127.0.0.1", 0) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await self._stop

    async def _handle(self, ws: ServerConnection) -> None:
        self.headers.append(dict(ws.request.headers.items()) if ws.request else {})
        async for raw in ws:
            frame = json.loads(raw)
            self.frames.append(frame)
            if self.expire_before_next_answer:
                self.expire_before_next_answer = False
                await ws.send(
                    json.dumps(
                        {
                            "result": "error",
                            "action": "error",
                            "error": "Insert session expired",
                            "detail": "idle",
                            "sessionId": frame.get("sessionId"),
                        }
                    )
                )
            if frame["action"] == "chunk" and self.close_1009_on_chunk:
                await ws.close(1009, "too big")
                return
            if frame["action"] == "chunk" and self.error_on_next_chunk is not None:
                error, self.error_on_next_chunk = self.error_on_next_chunk, None
                await ws.send(json.dumps({"result": "error", "action": "error", **error}))
                continue
            if frame["action"] == "chunk" and self.silent_on_chunk:
                continue
            await ws.send(json.dumps(self._answer(frame)))

    @staticmethod
    def _error(detail: str, session_id: str | None = None) -> dict[str, Any]:
        return {
            "result": "error",
            "action": "error",
            "error": "Insert session error",
            "detail": detail,
            "sessionId": session_id,
        }

    def _answer(self, frame: dict[str, Any]) -> dict[str, Any]:
        action = frame["action"]
        if action == "start":
            sid = frame.get("sessionId")
            if sid is None:
                self.counter += 1
                sid = f"srv-{self.counter}"
            if sid in self.sessions:
                return self._error(f"Session '{sid}' already exists", sid)
            options = frame.get("options", {})
            external = frame.get("transactionId")
            self.sessions[sid] = {
                "watermark": 0,
                "external": external,
                "inserted": 0,
                "mode": options.get("transactionMode", "per_stream"),
            }
            started = {
                "result": "ok",
                "action": "started",
                "sessionId": sid,
                "database": frame["database"],
                "transactionMode": "none" if external else options.get("transactionMode", "per_stream"),
            }
            if external:
                started["transactionId"] = external
            return started

        session = self.sessions.get(frame["sessionId"])
        if session is None:
            return self._error("Session not found", frame["sessionId"])
        if action == "chunk":
            records, seq = frame["records"], frame["chunkSeq"]
            if len(records) > MAX_ROWS:
                return self._error(f"Chunk {seq} carries {len(records)} records, more than the {MAX_ROWS} allowed")
            if seq <= session["watermark"]:
                return {
                    "result": "ok",
                    "action": "batchAck",
                    "chunkSeq": seq,
                    "replay": True,
                    "inserted": 0,
                    "failed": 0,
                }
            if seq != session["watermark"] + 1:
                return self._error(f"Chunk {seq} skips ahead of {session['watermark'] + 1}")
            if any(r.get("dup") for r in records) and session["mode"] in ("per_batch", "per_stream"):
                # The chunk's own transaction failed: a normal ack, watermark NOT advanced.
                return {
                    "result": "ok",
                    "action": "batchAck",
                    "chunkSeq": seq,
                    "received": len(records),
                    "inserted": 0,
                    "failed": len(records),
                    "errors": [{"rowIndex": -1, "code": "CONFLICT", "message": "duplicated key"}],
                }
            failed = sum(1 for r in records if r.get("@class") == "NoSuchType")
            session["watermark"] = seq
            session["inserted"] += len(records) - failed
            return {
                "result": "ok",
                "action": "batchAck",
                "chunkSeq": seq,
                "inserted": len(records) - failed,
                "failed": failed,
            }
        # commit / rollback
        del self.sessions[frame["sessionId"]]
        outcome = "detached" if session["external"] else action
        return {
            "result": "ok",
            "action": "committed",
            "outcome": outcome,
            "summary": {"inserted": session["inserted"], "externalTransaction": bool(session["external"])},
        }


@pytest.fixture
def fake() -> Iterator[FakeInsertServer]:
    server = FakeInsertServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def db(fake: FakeInsertServer) -> Iterator[ArcadeDBDatabase]:
    with ArcadeDBServer(base_url=fake.base_url, auth=basic_auth("root", "pw")) as srv:
        yield srv.db("mydb")


@pytest_asyncio.fixture
async def adb(fake: FakeInsertServer) -> AsyncIterator[AsyncArcadeDBDatabase]:
    async with AsyncArcadeDBServer(base_url=fake.base_url, auth=basic_auth("root", "pw")) as srv:
        yield srv.db("mydb")


def actions(fake: FakeInsertServer) -> list[str]:
    return [f["action"] for f in fake.frames]


# --------------------------------------------------------------------------------- synchronous


def test_the_start_frame_carries_the_options_and_the_credentials(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session(
        target_type="Person",
        conflict_mode="update",
        key_columns=["id"],
        update_columns_on_conflict=["name"],
        validate_only=True,
    ) as session:
        assert session.session_id == "srv-1"  # server-generated: none was sent
        assert session.transaction_mode == "per_stream"
        assert session.external_transaction_id is None

    start = fake.frames[0]
    assert start == {
        "action": "start",
        "database": "mydb",
        "options": {
            "targetType": "Person",
            "conflictMode": "update",
            "keyColumns": ["id"],
            "updateColumnsOnConflict": ["name"],
            "validateOnly": True,
        },
    }
    expected = "Basic " + base64.b64encode(b"root:pw").decode()
    assert {k.lower(): v for k, v in fake.headers[0].items()}["authorization"] == expected


def test_a_client_chosen_session_id_is_sent_and_a_taken_one_is_refused(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    with db.insert_session(session_id="batch-1") as first:
        assert first.session_id == "batch-1"
        with pytest.raises(InsertSessionError, match="already exists"), db.insert_session(session_id="batch-1"):
            pass


def test_chunk_sequence_starts_at_one_and_the_ack_reaches_the_callback_first(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    seen: list[int] = []
    with db.insert_session(target_type="Person", on_batch_ack=lambda ack: seen.append(ack["chunkSeq"])) as session:
        assert session.last_chunk_seq == 0
        assert session.send_chunk([{"name": "a"}, {"name": "b"}])["inserted"] == 2
        assert session.send_chunk([{"name": "c"}])["chunkSeq"] == 2
        assert session.last_chunk_seq == 2
        assert seen == [1, 2]
        committed = session.commit()

    assert committed["outcome"] == "commit"
    assert committed["summary"]["inserted"] == 3
    assert [f["chunkSeq"] for f in fake.frames if f["action"] == "chunk"] == [1, 2]
    assert not session.is_open


def test_a_chunk_refused_whole_reuses_its_sequence_and_the_session_carries_on(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    with db.insert_session(target_type="Person") as session:
        with pytest.raises(InsertSessionError, match=f"more than the {MAX_ROWS}") as refused:
            session.send_chunk([{"name": str(i)} for i in range(MAX_ROWS + 1)])
        assert refused.value.session_closed is False
        assert refused.value.frame is not None
        assert session.is_open
        assert session.last_chunk_seq == 0, "a refused chunk must not consume a sequence number"

        ack = session.send_chunk([{"name": "a"}, {"@class": "NoSuchType"}])
        assert (ack["chunkSeq"], ack["inserted"], ack["failed"]) == (1, 1, 1)
        session.commit()

    assert [f["chunkSeq"] for f in fake.frames if f["action"] == "chunk"] == [1, 1]


def test_a_per_record_class_travels_with_the_record(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session(target_type="Person") as session:
        session.send_chunk([{"name": "a"}, {"@class": "Company", "name": "x"}])
    chunk = next(f for f in fake.frames if f["action"] == "chunk")
    assert chunk["records"] == [{"name": "a"}, {"@class": "Company", "name": "x"}]


def test_joining_a_transaction_sends_it_and_commit_answers_detached(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    handle = ArcadeDBDatabase(db._client, "mydb", "AS-42")
    with handle.insert_session(
        target_type="Person", transaction_mode="per_row", join_current_transaction=True
    ) as session:
        assert session.transaction_mode == "none"
        assert session.external_transaction_id == "AS-42"
        session.send_chunk([{"name": "a"}])
        committed = session.commit()

    assert fake.frames[0]["transactionId"] == "AS-42"
    assert fake.frames[0]["options"]["transactionMode"] == "none", "the alias must be overridden, not merged"
    assert committed["outcome"] == "detached"
    assert committed["summary"]["externalTransaction"] is True


def test_joining_without_an_open_transaction_is_refused_before_any_connection(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    with pytest.raises(InsertSessionError, match="no open transaction"):
        db.insert_session(join_current_transaction=True)
    assert fake.headers == []


def test_close_rolls_back_an_open_session_and_is_idempotent(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    session = db.insert_session(target_type="Person").open()
    session.send_chunk([{"name": "a"}])
    session.close()
    session.close()

    assert actions(fake) == ["start", "chunk", "rollback"]
    assert fake.sessions == {}
    assert not session.is_open


def test_close_after_an_explicit_commit_sends_nothing_more(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session() as session:
        session.commit()
    assert actions(fake) == ["start", "commit"]


def test_a_closed_session_refuses_further_frames(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session() as session:
        session.commit()
        with pytest.raises(InsertSessionError, match="is closed"):
            session.send_chunk([{"name": "a"}])
        with pytest.raises(InsertSessionError, match="is closed"):
            session.commit()


def test_an_unsolicited_error_is_reported_not_skipped(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session(target_type="Person") as session:
        session.send_chunk([{"name": "a"}])
        fake.expire_before_next_answer = True
        with pytest.raises(InsertSessionError, match="idle") as err:
            session.send_chunk([{"name": "b"}])
        assert err.value.session_closed is True
        assert err.value.frame is not None
        assert err.value.frame["error"] == "Insert session expired"
        assert not session.is_open
        assert session.last_chunk_seq == 1


def test_a_frame_the_server_never_answers_times_out_and_ends_the_session(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    fake.silent_on_chunk = True
    with db.insert_session(timeout=0.3) as session:
        with pytest.raises(InsertSessionError, match="Timeout") as err:
            session.send_chunk([{"name": "a"}])
        assert err.value.session_closed is True
        assert not session.is_open
        assert session.last_chunk_seq == 0


def test_an_oversized_frame_is_a_1009_close_not_an_error_frame(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    fake.close_1009_on_chunk = True
    with db.insert_session() as session:
        with pytest.raises(InsertSessionError, match="1009") as err:
            session.send_chunk([{"name": "a"}])
        assert err.value.session_closed is True
        assert err.value.frame is None
        assert not session.is_open


def test_a_refused_connection_is_an_insert_session_error() -> None:
    with ArcadeDBServer(base_url="http://127.0.0.1:1") as srv, pytest.raises(InsertSessionError, match="opening"):
        srv.db("mydb").insert_session(timeout=2).open()


def test_opening_twice_is_refused(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session() as session, pytest.raises(InsertSessionError, match="already opened"):
        session.open()


# -------------------------------------------------------------------------------- asynchronous

pytestmark_async = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_async_session_round_trip(fake: FakeInsertServer, adb: AsyncArcadeDBDatabase) -> None:
    seen: list[int] = []
    async with adb.insert_session(
        target_type="Person", on_batch_ack=lambda ack: seen.append(ack["chunkSeq"])
    ) as session:
        assert session.session_id == "srv-1"
        assert (await session.send_chunk([{"name": "a"}, {"name": "b"}]))["inserted"] == 2
        assert (await session.send_chunk([{"name": "c"}]))["chunkSeq"] == 2
        committed = await session.commit()

    assert seen == [1, 2]
    assert committed["outcome"] == "commit"
    assert actions(fake) == ["start", "chunk", "chunk", "commit"]


@pytest.mark.asyncio
async def test_async_refused_chunk_reuses_its_sequence(fake: FakeInsertServer, adb: AsyncArcadeDBDatabase) -> None:
    async with adb.insert_session(target_type="Person") as session:
        with pytest.raises(InsertSessionError, match="more than") as refused:
            await session.send_chunk([{"n": i} for i in range(MAX_ROWS + 1)])
        assert refused.value.session_closed is False
        assert session.last_chunk_seq == 0
        assert (await session.send_chunk([{"n": 1}]))["chunkSeq"] == 1
    assert actions(fake)[-1] == "rollback"


@pytest.mark.asyncio
async def test_async_join_and_detached_commit(fake: FakeInsertServer, adb: AsyncArcadeDBDatabase) -> None:
    handle = AsyncArcadeDBDatabase(adb._client, "mydb", "AS-7")
    async with handle.insert_session(join_current_transaction=True) as session:
        assert session.external_transaction_id == "AS-7"
        assert (await session.commit())["outcome"] == "detached"

    with pytest.raises(InsertSessionError, match="no open transaction"):
        adb.insert_session(join_current_transaction=True)


@pytest.mark.asyncio
async def test_async_unsolicited_error_and_close_idempotent(fake: FakeInsertServer, adb: AsyncArcadeDBDatabase) -> None:
    session = await adb.insert_session().open()
    fake.expire_before_next_answer = True
    with pytest.raises(InsertSessionError, match="idle") as err:
        await session.send_chunk([{"name": "a"}])
    assert err.value.session_closed is True
    await session.close()
    await session.close()
    assert actions(fake) == ["start", "chunk"]


@pytest.mark.asyncio
async def test_async_timeout_and_1009(fake: FakeInsertServer, adb: AsyncArcadeDBDatabase) -> None:
    fake.silent_on_chunk = True
    async with adb.insert_session(timeout=0.3) as session:
        with pytest.raises(InsertSessionError, match="Timeout"):
            await session.send_chunk([{"name": "a"}])
        assert not session.is_open

    fake.silent_on_chunk = False
    fake.close_1009_on_chunk = True
    async with adb.insert_session() as session:
        with pytest.raises(InsertSessionError, match="1009"):
            await session.send_chunk([{"name": "a"}])


def test_a_whole_chunk_failure_is_an_ack_that_does_not_advance_the_sequence(
    fake: FakeInsertServer, db: ArcadeDBDatabase
) -> None:
    seen: list[dict[str, Any]] = []
    with db.insert_session(transaction_mode="per_batch", on_batch_ack=seen.append) as session:
        assert session.send_chunk([{"name": "a"}])["whole_chunk_failed"] is False
        ack = session.send_chunk([{"name": "b", "dup": True}])
        assert ack["whole_chunk_failed"] is True
        assert ack["failed"] == ack["received"] == 1
        assert session.last_chunk_seq == 1, "the server did not advance its watermark, so neither may the client"
        assert seen[-1] is ack, "the callback still sees a whole-chunk failure"
        assert session.is_open

        replay = session.send_chunk([{"name": "b"}])
        assert (replay["chunkSeq"], replay["inserted"], replay["whole_chunk_failed"]) == (2, 1, False)
        assert session.last_chunk_seq == 2
        session.commit()

    assert [f["chunkSeq"] for f in fake.frames if f["action"] == "chunk"] == [1, 2, 2]


@pytest.mark.asyncio
async def test_async_whole_chunk_failure_does_not_advance_the_sequence(
    fake: FakeInsertServer, adb: AsyncArcadeDBDatabase
) -> None:
    seen: list[dict[str, Any]] = []
    async with adb.insert_session(transaction_mode="per_batch", on_batch_ack=seen.append) as session:
        ack = await session.send_chunk([{"name": "b", "dup": True}])
        assert ack["whole_chunk_failed"] is True
        assert session.last_chunk_seq == 0
        assert seen == [ack]
        assert (await session.send_chunk([{"name": "b"}]))["chunkSeq"] == 1
        assert session.last_chunk_seq == 1

    assert [f["chunkSeq"] for f in fake.frames if f["action"] == "chunk"] == [1, 1]


ENDING_ERRORS = [
    {"error": "Security error", "detail": "User does not have access to database 'mydb'."},
    {"error": "Insert session error", "detail": "Insert session 'srv-1' not found or expired"},
    {"error": "Insert session error", "detail": "Insert session 'srv-1' is closed"},
    {"error": "Internal error", "detail": "boom"},
]


@pytest.mark.parametrize("error", ENDING_ERRORS, ids=lambda e: f"{e['error']}: {e['detail']}")
def test_an_error_that_ends_the_session_closes_it(
    fake: FakeInsertServer, db: ArcadeDBDatabase, error: dict[str, Any]
) -> None:
    with db.insert_session() as session:
        fake.error_on_next_chunk = error
        with pytest.raises(InsertSessionError) as err:
            session.send_chunk([{"name": "a"}])
        assert err.value.session_closed is True
        assert not session.is_open
        with pytest.raises(InsertSessionError, match="is closed"):
            session.send_chunk([{"name": "a"}])
    assert actions(fake) == ["start", "chunk"], "close() must not send rollback for a session that is gone"


@pytest.mark.parametrize("error", ENDING_ERRORS, ids=lambda e: f"{e['error']}: {e['detail']}")
@pytest.mark.asyncio
async def test_async_an_error_that_ends_the_session_closes_it(
    fake: FakeInsertServer, adb: AsyncArcadeDBDatabase, error: dict[str, Any]
) -> None:
    async with adb.insert_session() as session:
        fake.error_on_next_chunk = error
        with pytest.raises(InsertSessionError) as err:
            await session.send_chunk([{"name": "a"}])
        assert err.value.session_closed is True
        assert not session.is_open
    assert actions(fake) == ["start", "chunk"]


def test_a_skip_ahead_refusal_keeps_the_session_open(fake: FakeInsertServer, db: ArcadeDBDatabase) -> None:
    with db.insert_session() as session:
        fake.error_on_next_chunk = {"error": "Insert session error", "detail": "Chunk 3 skips ahead: expects 1 next"}
        with pytest.raises(InsertSessionError) as err:
            session.send_chunk([{"name": "a"}])
        assert err.value.session_closed is False
        assert session.is_open
        assert session.send_chunk([{"name": "a"}])["chunkSeq"] == 1


def test_an_interrupt_mid_exchange_ends_the_session(
    fake: FakeInsertServer, db: ArcadeDBDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db.insert_session() as session:
        ws = session._ws
        assert ws is not None

        def interrupted(*args: Any, **kwargs: Any) -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr(ws, "recv", interrupted)
        with pytest.raises(KeyboardInterrupt):
            session.send_chunk([{"name": "a"}])
        assert not session.is_open
        assert session.last_chunk_seq == 0
    assert actions(fake) == ["start", "chunk"], "close() must not send a rollback whose answer cannot be matched"
