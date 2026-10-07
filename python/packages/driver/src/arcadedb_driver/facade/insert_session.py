"""The duplex insert session on the server's `/ws` WebSocket endpoint: `InsertSession` (synchronous)
and `AsyncInsertSession`, opened with `ArcadeDBDatabase.insert_session()` /
`AsyncArcadeDBDatabase.insert_session()`.

Where `POST /api/v1/batch` fixes its commit policy by query parameters before the load starts, a
session lets the caller read the acknowledgement of chunk *n* and only THEN decide what to send
next - including whether to `commit()` or `rollback()` at all. It is the counterpart of the Java
client's `RemoteInsertSession` and of the gRPC `InsertBidirectional` shape.

`send_chunk` is request/response: it writes one `chunk` frame and returns the `batchAck` the server
answered it with. The protocol allows pipelining; this client deliberately does not, because a
loader that wants the acknowledgements to mean anything has to look at them.

Not thread-safe (nor task-safe), exactly like the database handle it comes from: one session
belongs to one thread, or for `AsyncInsertSession` to one task at a time.

The two classes duplicate each other on purpose (see python/CLAUDE.md): each carries its own full
docstrings. The rules that must not drift between them - frame shapes and the interpretation of an
answer - are in `_internal/insert_protocol.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping, Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any

from websockets.asyncio.client import ClientConnection as AsyncConnection
from websockets.asyncio.client import connect as aconnect
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.sync.client import ClientConnection as SyncConnection
from websockets.sync.client import connect as sconnect

from .._internal import insert_protocol as proto
from ..errors import InsertSessionError

if TYPE_CHECKING:
    from .._generated.client import Client

OUTCOME_DETACHED = proto.OUTCOME_DETACHED

#: How long one frame exchange may take, and how long the handshake may take, by default.
DEFAULT_TIMEOUT = 60.0


class _State:
    """Everything the two session classes share that is not I/O."""

    def __init__(
        self,
        client: Client,
        database: str,
        *,
        session_id: str | None,
        transaction_id: str | None,
        target_type: str | None,
        transaction_mode: str | None,
        conflict_mode: str | None,
        key_columns: Sequence[str] | None,
        update_columns_on_conflict: Sequence[str] | None,
        validate_only: bool,
        on_batch_ack: Callable[[dict[str, Any]], None] | None,
        timeout: float,
    ) -> None:
        self.url = proto.websocket_url(client._base_url)
        self.headers = dict(client._headers)
        self.ssl = proto.tls_context(self.url, client._verify_ssl)
        self.database = database
        self.requested_session_id = session_id
        self.session_id: str | None = session_id
        self.start = proto.build_start(
            database=database,
            session_id=session_id,
            transaction_id=transaction_id,
            target_type=target_type,
            transaction_mode=transaction_mode,
            conflict_mode=conflict_mode,
            key_columns=key_columns,
            update_columns_on_conflict=update_columns_on_conflict,
            validate_only=validate_only,
        )
        self.on_batch_ack = on_batch_ack
        self.timeout = timeout
        self.transaction_mode: str | None = None
        self.external_transaction_id: str | None = None
        self.chunk_seq = 0
        self.is_open = False
        self.opened = False

    def adopt_started(self, started: dict[str, Any]) -> None:
        self.session_id = started.get("sessionId") or self.session_id
        self.transaction_mode = started.get("transactionMode")
        self.external_transaction_id = started.get("transactionId")
        self.is_open = True

    def record_ack(self, seq: int, ack: dict[str, Any]) -> None:
        """Advances the sequence only for an ack the server's watermark advanced for too.

        A refused chunk never gets here (it raised), so its sequence is reused. A whole-chunk
        failure DOES get here - the server answers it with a normal `batchAck` - but the server
        did not move its watermark, so neither does this: the next `send_chunk` replays under the
        same `chunkSeq`. The ack is marked `whole_chunk_failed` either way.
        """
        whole = proto.is_whole_chunk_failure(ack)
        ack[proto.WHOLE_CHUNK_FAILED] = whole
        if not whole:
            self.chunk_seq = seq

    def check_open(self) -> None:
        if not self.is_open:
            raise InsertSessionError(
                f"The /ws insert session '{self.session_id}' is closed", session_id=self.session_id
            )


def _closed_error(session_id: str | None, err: ConnectionClosed) -> InsertSessionError:
    code = err.rcvd.code if err.rcvd is not None else None
    reason = err.rcvd.reason if err.rcvd is not None else ""
    hint = ""
    if code in (1009, None):
        # Against a real server an oversized frame surfaces as `code None`: the close frame is
        # sent while the client is still writing and the connection is reset before it is read.
        hint = (
            " (if this followed a chunk, the frame most likely exceeded the server's"
            " wsMaxInsertFrameSize: the server drops the connection rather than answering with an"
            " error frame, so the session is gone and was rolled back - send smaller chunks)"
        )
    return InsertSessionError(
        f"The server closed the /ws connection of insert session '{session_id}'"
        f" (code {code}{', ' + reason if reason else ''}){hint}",
        session_id=session_id,
    )


class InsertSession:
    """A duplex insert session on `/ws`, synchronous. Opened with `ArcadeDBDatabase.insert_session()`.

    Use it as a context manager - `with db.insert_session(target_type="Person") as session:` -
    which connects on entry and, on exit, rolls the session back if it is still open and closes the
    connection. `open()` does the connecting for a caller that wants no `with`; `close()` is then
    theirs to call.

    ```python
    with db.insert_session(target_type="Person") as session:
        ack = session.send_chunk([{"name": "a"}, {"name": "b"}])   # the batchAck, as a dict
        if ack["failed"] == 0:
            session.commit()
    ```

    Frames: `send_chunk` -> `batchAck`; `commit` / `rollback` -> `committed`. `session_id` is
    generated by the server unless the caller passed one; a caller-chosen id lives in ONE
    server-wide namespace (not per user, not per database), so two unrelated clients that both pick
    a convention like `batch-1` collide - leave it out unless the session must be nameable.

    `chunkSeq` is managed here: it starts at 1, is contiguous, and advances only after the server
    ACKNOWLEDGED the chunk. A chunk the server refuses as a whole - more rows than
    `arcadedb.server.wsMaxInsertChunkRows`, out of sequence - raises `InsertSessionError` with
    `session_closed=False`, leaves `last_chunk_seq` where it was, and the session usable: split the
    batch and send again, which takes the SAME sequence number. A row the server cannot apply is
    not a refusal at all: it is counted in the ack's `failed`, described in `errors`, and the rest
    of the chunk still goes in. A chunk whose TRANSACTION fails (`per_batch` only, e.g. a
    duplicate key reported on commit) is not a refusal either: it comes back as an ack with
    `whole_chunk_failed: True`, nothing in it durable, and `last_chunk_seq` unmoved because the
    server's watermark did not move - the next `send_chunk` replays that sequence number.

    A chunk over `arcadedb.server.wsMaxInsertFrameSize` BYTES is different: Undertow answers with a
    connection close (`1009`, though a real server surfaces it with no close code) instead of an
    `error` frame, so the connection (and with it the session, which the server rolls back) is
    gone and the failure is `InsertSessionError` with `session_closed=True`.

    An `error` frame can arrive at any time - the idle sweep rolls a session back and says so,
    unsolicited. Whichever call reads it raises `InsertSessionError` (`session_closed=True`)
    rather than skipping it for the answer it was waiting for.

    Every wait for an answer is bounded by `timeout` seconds (default 60). A timeout, a dropped
    connection or an out-of-step answer ends the session, since a later answer could no longer be
    matched to its frame; so does a `KeyboardInterrupt` (or any other `BaseException`) raised
    mid-exchange, after which `close()` only closes the connection and the server rolls the
    session back. `send` itself is not bounded by `timeout` (the synchronous `websockets` client
    has no send timeout).

    Some `error` frames end the session, others only refuse one frame: `session_closed` on the
    `InsertSessionError` says which. It is `True` for `"Insert session expired"`,
    `"Security error"`, `"Internal error"` and a `not found or expired` / `is closed` detail.

    Joining a transaction: `insert_session(join_current_transaction=True)`, called on the handle
    that `db.transaction()` yields, writes into that HTTP transaction instead of opening its own
    (`transaction_mode` is then `"none"`). `commit()` and `rollback()` then answer
    `outcome == "detached"`: neither decides anything, the transaction block does - rows become
    durable only when it exits cleanly, and a block that raises undoes them.

    Not thread-safe; one session per thread.
    """

    def __init__(self, client: Client, database: str, **kwargs: Any) -> None:
        self._s = _State(client, database, **kwargs)
        self._ws: SyncConnection | None = None
        # Entering `connect()` as a context manager is what websockets 17 asks for; a bare call
        # warns that it will stop returning the connection directly.
        self._stack = contextlib.ExitStack()

    @property
    def session_id(self) -> str | None:
        """The id this session is known by on the server: generated by it unless the caller chose one."""
        return self._s.session_id

    @property
    def database(self) -> str:
        return self._s.database

    @property
    def transaction_mode(self) -> str | None:
        """The commit policy the server echoed in `started`, which may differ from the alias sent."""
        return self._s.transaction_mode

    @property
    def external_transaction_id(self) -> str | None:
        """The HTTP transaction this session joined, or `None` when it manages its own."""
        return self._s.external_transaction_id

    @property
    def last_chunk_seq(self) -> int:
        """How many chunks the server has acknowledged. The next one is this plus one."""
        return self._s.chunk_seq

    @property
    def is_open(self) -> bool:
        return self._s.is_open

    def open(self) -> InsertSession:
        """Connects, sends `start` and returns this session once the server answered `started`.

        Raises `InsertSessionError` when the connection or the `start` frame is refused. Called by
        `__enter__`; calling it twice raises.
        """
        s = self._s
        if s.opened:
            raise InsertSessionError("The /ws insert session was already opened", session_id=s.session_id)
        s.opened = True
        try:
            self._ws = self._stack.enter_context(
                sconnect(
                    s.url,
                    additional_headers=s.headers,
                    ssl=s.ssl,
                    open_timeout=s.timeout,
                    close_timeout=s.timeout,
                    max_size=None,
                )
            )
        except (OSError, WebSocketException, TimeoutError) as err:
            raise InsertSessionError(
                f"Error on opening the /ws insert session on {s.url}: {err}", session_id=s.session_id
            ) from err
        try:
            started = self._exchange(s.start, "started")
        except BaseException:
            self._drop()
            raise
        s.adopt_started(started)
        return self

    def send_chunk(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Sends one chunk and returns the `batchAck` the server answered with, after handing it to
        `on_batch_ack` if one was given.

        A record takes its type from its own `"@class"` or from the session's `target_type`; an edge
        names its endpoints with `"@from"` / `"@to"`. The ack carries `chunkSeq`, `received`,
        `inserted`, `updated`, `ignored`, `failed`, `errors` and, for a replay, `replay: true` with
        zero tallies - plus `whole_chunk_failed`, which this client adds (snake_case because the
        server never sends it).

        `whole_chunk_failed` is `True` when the chunk's transaction failed as a whole - `per_batch`
        only, since each chunk commits on its own there; the server reports it as
        `failed == received` with an `errors` entry at `rowIndex` -1. (Under `per_stream` nothing
        commits per chunk: the same duplicate key fails the `commit()` frame instead, and the
        session is gone.) That is an ack, not a refusal: nothing is raised and `on_batch_ack` still
        sees it, but nothing in the chunk is durable and the server did not advance its watermark,
        so `last_chunk_seq` does not move either - the next `send_chunk` is the replay of this
        sequence number, with whatever records the caller sends (normally the same ones, fixed).

        Raises `InsertSessionError` when the server refused the chunk; check `session_closed` to
        tell a refusal that left the session usable from one that ended it.
        """
        s = self._s
        s.check_open()
        seq = s.chunk_seq + 1
        assert s.session_id is not None
        ack = self._exchange(proto.build_chunk(s.session_id, seq, records), "batchAck")
        s.record_ack(seq, ack)
        if s.on_batch_ack is not None:
            s.on_batch_ack(ack)
        return ack

    def commit(self) -> dict[str, Any]:
        """Ends the session and commits what it wrote, returning the `committed` frame.

        On a session that joined a transaction, commits nothing: `outcome` is `"detached"`.
        The session is closed afterwards whatever the server said - a commit the engine refused has
        already rolled it back.
        """
        return self._finish("commit")

    def rollback(self) -> dict[str, Any]:
        """Ends the session and discards what it wrote, returning the `committed` frame.

        Only a `per_stream` session can genuinely undo chunks it already acknowledged
        (`summary.partialCommit` says so). On a session that joined a transaction, discards nothing:
        `outcome` is `"detached"`, and the transaction block decides.
        """
        return self._finish("rollback")

    def close(self) -> None:
        """Rolls the session back if it is still open, then closes the connection. Idempotent, so it
        is safe after an explicit `commit()`. A failure while rolling back is swallowed: the
        connection closing makes the server roll the session back anyway."""
        if self._s.is_open:
            with contextlib.suppress(Exception):
                self.rollback()
        self._drop()

    def __enter__(self) -> InsertSession:
        return self.open()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _finish(self, action: str) -> dict[str, Any]:
        s = self._s
        s.check_open()
        assert s.session_id is not None
        try:
            return self._exchange(proto.build_finish(action, s.session_id), "committed")
        finally:
            s.is_open = False

    def _drop(self) -> None:
        self._s.is_open = False
        self._ws = None
        with contextlib.suppress(Exception):
            self._stack.close()

    def _exchange(self, frame: dict[str, Any], expected: str) -> dict[str, Any]:
        s = self._s
        ws = self._ws
        assert ws is not None
        try:
            ws.send(proto.encode(frame))
        except ConnectionClosed as err:
            s.is_open = False
            raise _closed_error(s.session_id, err) from err
        except (OSError, WebSocketException) as err:
            s.is_open = False
            raise InsertSessionError(
                f"Error on sending a /ws insert frame for session '{s.session_id}': {err}", session_id=s.session_id
            ) from err
        except BaseException:
            # KeyboardInterrupt and the like: the frame may or may not have gone out, and its
            # answer would be read as the answer to the next one.
            s.is_open = False
            raise
        try:
            raw = ws.recv(timeout=s.timeout)
        except TimeoutError as err:
            s.is_open = False
            raise InsertSessionError(
                f"Timeout of {s.timeout}s waiting for the answer to a frame of /ws insert session '{s.session_id}'",
                session_id=s.session_id,
            ) from err
        except ConnectionClosed as err:
            s.is_open = False
            raise _closed_error(s.session_id, err) from err
        except BaseException:
            # KeyboardInterrupt and the like: the answer may still arrive and would be read as the
            # answer to the next frame.
            s.is_open = False
            raise
        try:
            return proto.interpret(raw, expected, s.session_id)
        except InsertSessionError as err:
            if err.session_closed:
                s.is_open = False
            raise


class AsyncInsertSession:
    """A duplex insert session on `/ws`, asynchronous. Opened with `AsyncArcadeDBDatabase.insert_session()`.

    The `asyncio` twin of `InsertSession`: same frames, same rules, awaited. Use it as
    `async with db.insert_session(target_type="Person") as session:`, which connects on entry and,
    on exit, rolls the session back if it is still open and closes the connection. `await open()`
    does the connecting for a caller that wants no `async with`; `await close()` is then theirs.

    ```python
    async with db.insert_session(target_type="Person") as session:
        ack = await session.send_chunk([{"name": "a"}, {"name": "b"}])
        if ack["failed"] == 0:
            await session.commit()
    ```

    `session_id` is generated by the server unless the caller passed one; a caller-chosen id lives
    in ONE server-wide namespace (not per user, not per database), so two unrelated clients that
    both pick a convention like `batch-1` collide - leave it out unless the session must be
    nameable.

    `chunkSeq` is managed here: it starts at 1, is contiguous, and advances only after the server
    ACKNOWLEDGED the chunk. A chunk the server refuses as a whole - more rows than
    `arcadedb.server.wsMaxInsertChunkRows`, out of sequence - raises `InsertSessionError` with
    `session_closed=False`, leaves `last_chunk_seq` where it was, and the session usable: split the
    batch and send again under the SAME sequence number. A row the server cannot apply is not a
    refusal: it is counted in the ack's `failed`, described in `errors`, and the rest of the chunk
    still goes in. A chunk whose TRANSACTION fails (`per_batch` only) comes back as an
    ack with `whole_chunk_failed: True` and leaves `last_chunk_seq` unmoved, so the next
    `send_chunk` replays that sequence number. A chunk over `arcadedb.server.wsMaxInsertFrameSize`
    BYTES is answered with a connection close (`1009`, often with no code on the wire), not an
    `error` frame: the connection and the session are gone (`session_closed=True`).

    An `error` frame can arrive at any time (the idle sweep rolling the session back); whichever
    awaited call reads it raises `InsertSessionError` (`session_closed=True`) rather than skipping
    it. Every wait for an answer is bounded by `timeout` seconds (default 60) via
    `asyncio.wait_for`, and so is each send; a timeout, a dropped connection or an out-of-step
    answer ends the session, and so does an `error` frame of the kind that ends it (`"Insert
    session expired"`, `"Security error"`, `"Internal error"`, a `not found or expired` / `is
    closed` detail - `session_closed` says which). Cancelling a call mid-exchange (task
    cancellation) also ends the
    session, for the same reason: its answer can no longer be matched to its frame - `close()`
    then only closes the connection, and the server rolls the session back.

    Joining a transaction: `insert_session(join_current_transaction=True)` on the handle that
    `db.transaction()` yields writes into that HTTP transaction instead of opening its own
    (`transaction_mode` is then `"none"`); `commit()` / `rollback()` answer `outcome ==
    "detached"` and the `async with db.transaction()` block decides.

    Not safe for concurrent use: one session per task, with one call in flight at a time.
    """

    def __init__(self, client: Client, database: str, **kwargs: Any) -> None:
        self._s = _State(client, database, **kwargs)
        self._ws: AsyncConnection | None = None
        self._stack = contextlib.AsyncExitStack()

    @property
    def session_id(self) -> str | None:
        """The id this session is known by on the server: generated by it unless the caller chose one."""
        return self._s.session_id

    @property
    def database(self) -> str:
        return self._s.database

    @property
    def transaction_mode(self) -> str | None:
        """The commit policy the server echoed in `started`, which may differ from the alias sent."""
        return self._s.transaction_mode

    @property
    def external_transaction_id(self) -> str | None:
        """The HTTP transaction this session joined, or `None` when it manages its own."""
        return self._s.external_transaction_id

    @property
    def last_chunk_seq(self) -> int:
        """How many chunks the server has acknowledged. The next one is this plus one."""
        return self._s.chunk_seq

    @property
    def is_open(self) -> bool:
        return self._s.is_open

    async def open(self) -> AsyncInsertSession:
        """Connects, sends `start` and returns this session once the server answered `started`.

        Raises `InsertSessionError` when the connection or the `start` frame is refused. Called by
        `__aenter__`; calling it twice raises.
        """
        s = self._s
        if s.opened:
            raise InsertSessionError("The /ws insert session was already opened", session_id=s.session_id)
        s.opened = True
        try:
            self._ws = await self._stack.enter_async_context(
                aconnect(
                    s.url,
                    additional_headers=s.headers,
                    ssl=s.ssl,
                    open_timeout=s.timeout,
                    close_timeout=s.timeout,
                    max_size=None,
                )
            )
        except (OSError, WebSocketException, TimeoutError) as err:
            raise InsertSessionError(
                f"Error on opening the /ws insert session on {s.url}: {err}", session_id=s.session_id
            ) from err
        try:
            started = await self._exchange(s.start, "started")
        except BaseException:
            await self._drop()
            raise
        s.adopt_started(started)
        return self

    async def send_chunk(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Sends one chunk and returns the `batchAck` the server answered with, after handing it to
        `on_batch_ack` if one was given.

        A record takes its type from its own `"@class"` or from the session's `target_type`; an edge
        names its endpoints with `"@from"` / `"@to"`. The ack carries `chunkSeq`, `received`,
        `inserted`, `updated`, `ignored`, `failed`, `errors` and, for a replay, `replay: true` with
        zero tallies - plus `whole_chunk_failed`, which this client adds (snake_case because the
        server never sends it).

        `whole_chunk_failed` is `True` when the chunk's transaction failed as a whole - `per_batch`
        only, since each chunk commits on its own there; the server reports it as
        `failed == received` with an `errors` entry at `rowIndex` -1. (Under `per_stream` nothing
        commits per chunk: the same duplicate key fails the `commit()` frame instead, and the
        session is gone.) That is an ack, not a refusal: nothing is raised and `on_batch_ack` still
        sees it, but nothing in the chunk is durable and the server did not advance its watermark,
        so `last_chunk_seq` does not move either - the next `send_chunk` is the replay of this
        sequence number, with whatever records the caller sends (normally the same ones, fixed).

        Raises `InsertSessionError` when the server refused the chunk; check `session_closed` to
        tell a refusal that left the session usable from one that ended it.
        """
        s = self._s
        s.check_open()
        seq = s.chunk_seq + 1
        assert s.session_id is not None
        ack = await self._exchange(proto.build_chunk(s.session_id, seq, records), "batchAck")
        s.record_ack(seq, ack)
        if s.on_batch_ack is not None:
            s.on_batch_ack(ack)
        return ack

    async def commit(self) -> dict[str, Any]:
        """Ends the session and commits what it wrote, returning the `committed` frame.

        On a session that joined a transaction, commits nothing: `outcome` is `"detached"`.
        The session is closed afterwards whatever the server said - a commit the engine refused has
        already rolled it back.
        """
        return await self._finish("commit")

    async def rollback(self) -> dict[str, Any]:
        """Ends the session and discards what it wrote, returning the `committed` frame.

        Only a `per_stream` session can genuinely undo chunks it already acknowledged
        (`summary.partialCommit` says so). On a session that joined a transaction, discards nothing:
        `outcome` is `"detached"`, and the transaction block decides.
        """
        return await self._finish("rollback")

    async def close(self) -> None:
        """Rolls the session back if it is still open, then closes the connection. Idempotent, so it
        is safe after an explicit `commit()`. A failure while rolling back is swallowed: the
        connection closing makes the server roll the session back anyway."""
        if self._s.is_open:
            with contextlib.suppress(Exception):
                await self.rollback()
        await self._drop()

    async def __aenter__(self) -> AsyncInsertSession:
        return await self.open()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def _finish(self, action: str) -> dict[str, Any]:
        s = self._s
        s.check_open()
        assert s.session_id is not None
        try:
            return await self._exchange(proto.build_finish(action, s.session_id), "committed")
        finally:
            s.is_open = False

    async def _drop(self) -> None:
        self._s.is_open = False
        self._ws = None
        with contextlib.suppress(Exception):
            await self._stack.aclose()

    async def _exchange(self, frame: dict[str, Any], expected: str) -> dict[str, Any]:
        s = self._s
        ws = self._ws
        assert ws is not None
        try:
            await asyncio.wait_for(ws.send(proto.encode(frame)), s.timeout)
            raw = await asyncio.wait_for(ws.recv(), s.timeout)
        except asyncio.TimeoutError as err:
            s.is_open = False
            raise InsertSessionError(
                f"Timeout of {s.timeout}s on a frame of /ws insert session '{s.session_id}'",
                session_id=s.session_id,
            ) from err
        except ConnectionClosed as err:
            s.is_open = False
            raise _closed_error(s.session_id, err) from err
        except (OSError, WebSocketException) as err:
            s.is_open = False
            raise InsertSessionError(
                f"Error on a /ws insert frame for session '{s.session_id}': {err}", session_id=s.session_id
            ) from err
        except BaseException:
            # Cancellation: the answer to this frame may still arrive and would be read as the
            # answer to the next one.
            s.is_open = False
            raise
        try:
            return proto.interpret(raw, expected, s.session_id)
        except InsertSessionError as err:
            if err.session_closed:
                s.is_open = False
            raise
