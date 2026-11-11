"""`ArcadeDBServer(transport="http.client")` against an in-process fake ArcadeDB server (issue #187).

The fake is a `ThreadingHTTPServer` speaking HTTP/1.1 with keep-alive and the few endpoints the driver's
`query`, `command` and transaction calls use. Almost every case runs once per transport, with the same
assertions: the two transports must return the same envelopes, raise the same exceptions and put the same
request on the wire (apart from `User-Agent`). No Docker and no Java is involved.
"""

from __future__ import annotations

import gzip
import http.client
import json
import re
import socket
import threading
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal

import httpx
import pytest
from arcadedb_driver import ArcadeDBDatabase, ArcadeDBError, ArcadeDBServer, QueryEnvelope, basic_auth
from arcadedb_driver._internal.http_client import HttpClientTransport, TransportName, _Slot, encode_json

ERROR_BODY = {
    "error": "Encountered an error",
    "exception": "com.arcadedb.SomeException",
    "detail": "line 1",
    "exceptionArgs": "arg",
}
ENDPOINT = re.compile(r"/api/v1/(query|command|begin|commit|rollback)/")
CloseMode = Literal["keep", "silent", "announced"]


@dataclass
class Seen:
    """One request the fake received, with the connection that carried it."""

    method: str
    path: str
    headers: dict[str, str]  # names lower-cased
    body: bytes
    connection: int

    @property
    def payload(self) -> Any:
        return json.loads(self.body)


class FakeArcadeDB:
    """Just enough ArcadeDB over HTTP/1.1 keep-alive, recording every request it receives.

    What a `query`/`command` statement does is chosen by its text: `ROWS:<n>` answers n rows, `EMPTY` none,
    `TRUNC` as many rows as `limit` with `truncated`, `EXPLAIN` an execution plan, `ERR:<status>` the server's
    error body, `SLOW` waits `delay` seconds first, `HANGUP` closes the connection without answering, `PARTIAL`
    sends the headers and a tenth of the body; any other text is echoed back as the single row.
    """

    def __init__(self) -> None:
        self.seen: list[Seen] = []
        self.accepted = 0
        self.closed = 0
        self.close_mode: CloseMode = "keep"
        self.gzip_answers = False
        self.delay = 0.6
        self.sessions: set[str] = set()
        self._cond = threading.Condition()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            number = 0

            def setup(self) -> None:
                super().setup()
                with fake._cond:
                    fake.accepted += 1
                    self.number = fake.accepted

            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                fake._record(self, b"")
                fake._reply(self, 204 if self.path.endswith("/api/v1/ready") else 404)

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                fake._record(self, body)
                fake._route(self, body)

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def shutdown_request(self, request: Any) -> None:
                super().shutdown_request(request)
                with fake._cond:
                    fake.closed += 1
                    fake._cond.notify_all()

            def handle_error(self, request: Any, client_address: Any) -> None:
                pass  # a client that timed out and left is expected here

        self._server = Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def wait_closed(self, count: int) -> None:
        """Blocks until the server has closed `count` connections, so the client's next call finds one stale."""
        with self._cond:
            assert self._cond.wait_for(lambda: self.closed >= count, timeout=5), "the server did not close in time"

    def commands(self) -> list[str]:
        return [s.payload["command"] for s in self.seen if ENDPOINT.search(s.path) and s.body.startswith(b"{")]

    def _record(self, handler: BaseHTTPRequestHandler, body: bytes) -> None:
        headers = {name.lower(): value for name, value in handler.headers.items()}
        seen = Seen(handler.command, handler.path, headers, body, getattr(handler, "number", 0))
        with self._cond:
            self.seen.append(seen)

    def _route(self, handler: BaseHTTPRequestHandler, body: bytes) -> None:
        match = ENDPOINT.search(handler.path)
        endpoint = match.group(1) if match else ""
        if endpoint in ("query", "command"):
            self._statement(handler, json.loads(body))
        elif endpoint == "begin":
            with self._cond:
                session = f"AU-{len(self.sessions) + len(self.seen)}"
                self.sessions.add(session)
            self._reply(handler, 204, headers={"arcadedb-session-id": session})
        elif endpoint in ("commit", "rollback"):
            session_id = handler.headers.get("arcadedb-session-id", "")
            if session_id in self.sessions:
                self.sessions.discard(session_id)
                self._reply(handler, 204)
            else:
                self._reply(handler, 404, ERROR_BODY)
        else:
            self._reply(handler, 404, ERROR_BODY)

    def _statement(self, handler: BaseHTTPRequestHandler, request: dict[str, Any]) -> None:
        command: str = request["command"]
        limit = request.get("limit")
        if command == "HANGUP":
            handler.close_connection = True
            return
        if command == "PARTIAL":
            handler.send_response(200)
            handler.send_header("Content-Length", "100")
            handler.end_headers()
            handler.wfile.write(b"0123456789")
            handler.close_connection = True
            return
        if command == "SLOW":
            time.sleep(self.delay)
        if command.startswith("ERR:"):
            self._reply(handler, int(command[4:]), ERROR_BODY, {"X-Request-Id": "req-1", "Retry-After": "3"})
            return
        if handler.headers.get("Accept") == "application/x-ndjson":
            lines = [
                {"record": {"a": 1}},
                {"record": {"a": 2}},
                {"stats": {"limit": 20000, "returned": 2, "truncated": False}},
            ]
            self._reply(handler, 200, raw="".join(json.dumps(line) + "\n" for line in lines).encode())
            return
        truncated = False
        if command == "EXPLAIN":
            answer: dict[str, Any] = {
                "result": [],
                "limit": 20000,
                "returned": 0,
                "truncated": False,
                "explain": "plan",
                "explainPlan": {"steps": []},
            }
            self._reply(handler, 200, answer)
            return
        if command == "EMPTY":
            rows: list[dict[str, Any]] = []
        elif command.startswith("ROWS:"):
            rows = [{"i": i, "@rid": f"#1:{i}"} for i in range(int(command[5:]))]
        elif command == "TRUNC":
            rows = [{"i": i} for i in range(int(limit or 0))]
            truncated = True
        else:
            rows = [{"echo": command, "params": request.get("params"), "language": request["language"]}]
        answer = {
            "result": rows,
            "limit": 20000 if limit is None else limit,
            "returned": len(rows),
            "truncated": truncated,
        }
        self._reply(handler, 200, answer)

    def _reply(
        self,
        handler: BaseHTTPRequestHandler,
        status: int,
        payload: Any = None,
        headers: dict[str, str] | None = None,
        raw: bytes | None = None,
    ) -> None:
        data = raw if raw is not None else (b"" if payload is None else json.dumps(payload).encode())
        handler.send_response(status)
        if data:
            handler.send_header("Content-Type", "application/x-ndjson" if raw is not None else "application/json")
            if self.gzip_answers and "gzip" in handler.headers.get("Accept-Encoding", ""):
                data = gzip.compress(data)
                handler.send_header("Content-Encoding", "gzip")
        for name, value in (headers or {}).items():
            handler.send_header(name, value)
        if status != 204:
            handler.send_header("Content-Length", str(len(data)))
        if self.close_mode == "announced":
            handler.send_header("Connection", "close")
        elif self.close_mode == "silent":
            handler.close_connection = True
        handler.end_headers()
        handler.wfile.write(data)


@pytest.fixture
def fake() -> Iterator[FakeArcadeDB]:
    server = FakeArcadeDB()
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(params=["httpx", "http.client"])
def transport(request: pytest.FixtureRequest) -> TransportName:
    return "http.client" if request.param == "http.client" else "httpx"


def connect(fake: FakeArcadeDB, transport: TransportName, **kwargs: Any) -> ArcadeDBServer:
    return ArcadeDBServer(
        base_url=kwargs.pop("base_url", fake.url), auth=basic_auth("root", "pw"), transport=transport, **kwargs
    )


def outcome(db: ArcadeDBDatabase, command: str, **kwargs: Any) -> tuple[Any, ...]:
    """What a caller can observe of one statement: the envelope, or the exception with every field it carries."""
    try:
        envelope = db.query(language="sql", command=command, **kwargs)
    except ArcadeDBError as err:
        return (
            "raised",
            err.status,
            err.error,
            err.exception,
            err.detail,
            err.exception_args,
            err.request_id,
            err.retry_after,
        )
    return ("answered", envelope)


def test_the_default_transport_is_httpx(fake: FakeArcadeDB) -> None:
    with ArcadeDBServer(base_url=fake.url) as srv:
        srv.db("d").query(language="sql", command="SELECT 1")
    assert fake.seen[0].headers["user-agent"].startswith("python-httpx/")


def test_http_client_sends_its_own_user_agent_and_httpx_defaults(fake: FakeArcadeDB) -> None:
    with connect(fake, "http.client") as srv:
        srv.db("d").query(language="sql", command="SELECT 1")
    headers = fake.seen[0].headers
    assert headers["user-agent"] == "arcadedb-driver"
    assert (headers["accept"], headers["accept-encoding"], headers["connection"]) == (
        "*/*",
        "gzip, deflate",
        "keep-alive",
    )


def test_a_one_row_read(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        envelope = srv.db("mydb").query(language="sql", command="SELECT FROM V WHERE a = :a", params={"a": 1})
    assert envelope == QueryEnvelope(
        result=[{"echo": "SELECT FROM V WHERE a = :a", "params": {"a": 1}, "language": "sql"}],
        limit=20000,
        returned=1,
        truncated=False,
    )
    sent = fake.seen[0]
    assert (sent.method, sent.path) == ("POST", "/api/v1/query/mydb")
    assert sent.payload == {"command": "SELECT FROM V WHERE a = :a", "language": "sql", "params": {"a": 1}}
    assert sent.headers["authorization"] == "Basic cm9vdDpwdw=="
    assert sent.headers["content-type"] == "application/json"
    assert int(sent.headers["content-length"]) == len(sent.body)


def test_command_goes_to_the_command_endpoint_and_a_limit_is_sent(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        envelope = srv.db("mydb").command(language="cypher", command="MATCH (n) RETURN n", limit=7)
    assert (envelope.limit, envelope.returned) == (7, 1)
    assert (fake.seen[0].path, fake.seen[0].payload) == (
        "/api/v1/command/mydb",
        {"command": "MATCH (n) RETURN n", "language": "cypher", "limit": 7},
    )


def test_a_hundred_row_read(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        envelope = srv.db("d").query(language="sql", command="ROWS:100")
    assert envelope.returned == 100
    assert envelope.result == [{"i": i, "@rid": f"#1:{i}"} for i in range(100)]


def test_an_empty_result(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        envelope = srv.db("d").query(language="sql", command="EMPTY")
    assert envelope == QueryEnvelope(result=[], limit=20000, returned=0, truncated=False)


def test_a_truncated_result(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        envelope = srv.db("d").query(language="sql", command="TRUNC", limit=5)
    assert (envelope.limit, envelope.returned, envelope.truncated) == (5, 5, True)
    assert fake.seen[0].payload["limit"] == 5


def test_an_explain_answer_takes_the_generated_parse(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        envelope = srv.db("d").query(language="sql", command="EXPLAIN")
    assert (envelope.result, envelope.explain, envelope.explain_plan) == ([], "plan", {"steps": []})


@pytest.mark.parametrize("status", [400, 401, 404, 409, 500, 503])
def test_an_error_status_is_mapped_to_arcadedb_error(fake: FakeArcadeDB, transport: TransportName, status: int) -> None:
    with connect(fake, transport) as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("d").query(language="sql", command=f"ERR:{status}")
    err = caught.value
    assert (err.status, err.error, err.exception, err.detail, err.exception_args) == (
        status,
        "Encountered an error",
        "com.arcadedb.SomeException",
        "line 1",
        "arg",
    )
    assert (err.request_id, err.retry_after) == ("req-1", 3)


def test_the_two_transports_answer_the_same(fake: FakeArcadeDB) -> None:
    statements = ["SELECT 1", "EMPTY", "ROWS:100", "TRUNC", "EXPLAIN", "ERR:409", "ERR:500"]
    results: dict[str, list[tuple[Any, ...]]] = {}
    for name in ("httpx", "http.client"):
        transport: TransportName = "http.client" if name == "http.client" else "httpx"
        with connect(fake, transport) as srv:
            results[name] = [outcome(srv.db("d"), command, limit=3) for command in statements]
    assert results["httpx"] == results["http.client"]
    sent = [(s.method, s.path, s.payload, s.headers["authorization"]) for s in fake.seen]
    assert sent[: len(statements)] == sent[len(statements) :]


def test_a_query_tag_is_sent_per_call_and_only_when_given(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        db = srv.db("d")
        db.query(language="sql", command="SELECT 1", query_tag="job-7")
        db.query(language="sql", command="SELECT 2")
    assert fake.seen[0].headers["x-arcadedb-query-tag"] == "job-7"
    assert "x-arcadedb-query-tag" not in fake.seen[1].headers


def test_a_database_name_is_percent_encoded_in_the_path(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        srv.db("my db/ü").query(language="sql", command="SELECT 1")
    assert fake.seen[0].path == "/api/v1/query/my%20db%2F%C3%BC"


def test_a_renamed_database_handle_uses_the_new_path(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        db = srv.db("one")
        db.query(language="sql", command="SELECT 1")
        db.name = "two"
        db.query(language="sql", command="SELECT 1")
    assert [s.path for s in fake.seen] == ["/api/v1/query/one", "/api/v1/query/two"]


def test_a_base_url_path_is_put_before_the_request_path(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport, base_url=f"{fake.url}/arcade/") as srv:
        srv.db("d").query(language="sql", command="SELECT 1")
    assert fake.seen[0].path == "/arcade/api/v1/query/d"


def test_a_transaction_runs_begin_statements_and_commit(fake: FakeArcadeDB, transport: TransportName) -> None:
    with (
        connect(fake, transport) as srv,
        srv.db("d").transaction(query_tag="tx-tag", isolation_level="REPEATABLE_READ") as tx,
    ):
        tx.command(language="sql", command="INSERT INTO A SET x = 1")
        tx.query(language="sql", command="SELECT FROM A")
    paths = [s.path.rsplit("/", 2)[-2] for s in fake.seen]
    assert paths == ["begin", "command", "query", "commit"]
    begin, command, query, commit = fake.seen
    assert begin.payload == {"isolationLevel": "REPEATABLE_READ"}
    assert begin.headers["x-arcadedb-query-tag"] == "tx-tag"
    session = command.headers["arcadedb-session-id"]
    assert session and query.headers["arcadedb-session-id"] == session == commit.headers["arcadedb-session-id"]
    assert "x-arcadedb-query-tag" not in command.headers


def test_statements_outside_the_transaction_carry_no_session(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        db = srv.db("d")
        with db.transaction():
            db.query(language="sql", command="SELECT outer")
    outer = next(s for s in fake.seen if s.path.endswith("/query/d"))
    assert "arcadedb-session-id" not in outer.headers


def test_a_block_that_raises_rolls_back_and_reraises(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv, pytest.raises(ValueError, match="boom"), srv.db("d").transaction():
        raise ValueError("boom")
    assert [s.path.rsplit("/", 2)[-2] for s in fake.seen] == ["begin", "rollback"]
    assert fake.sessions == set()


def test_a_failed_commit_raises_arcadedb_error(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv, pytest.raises(ArcadeDBError) as caught, srv.db("d").transaction():
        fake.sessions.clear()  # the server forgot the session, as after `terminate transaction`
    assert (caught.value.status, caught.value.error) == (404, "Encountered an error")
    assert [s.path.rsplit("/", 2)[-2] for s in fake.seen] == ["begin", "commit", "rollback"]


@pytest.mark.parametrize("mode", ["silent", "announced"])
def test_a_closed_connection_never_fails_a_call_and_never_sends_one_twice(
    fake: FakeArcadeDB, transport: TransportName, mode: CloseMode
) -> None:
    fake.close_mode = mode
    calls = 6
    with connect(fake, transport) as srv:
        db = srv.db("d")
        for i in range(calls):
            answer = db.query(language="sql", command=f"SELECT {i}")
            assert answer.result[0]["echo"] == f"SELECT {i}"
            fake.wait_closed(i + 1)  # the next call finds its connection already closed by the server
        stale = srv._transport.stale_retries if srv._transport is not None else None
    assert fake.commands() == [f"SELECT {i}" for i in range(calls)]  # each statement arrived exactly once
    assert fake.accepted == calls
    if transport == "http.client":
        # With a silent close the idle connection looks usable, so every call after the first is resent once on
        # a new connection (the first send reached a closed socket). An announced close is seen by http.client.
        assert stale == (calls - 1 if mode == "silent" else 0)


def test_a_hang_up_on_a_new_connection_is_not_retried(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv, pytest.raises(httpx.RemoteProtocolError):
        srv.db("d").query(language="sql", command="HANGUP")
    assert fake.commands() == ["HANGUP"]


def test_a_hang_up_on_a_reused_connection_is_resent_once_and_then_raised(fake: FakeArcadeDB) -> None:
    with connect(fake, "http.client") as srv:
        db = srv.db("d")
        db.query(language="sql", command="SELECT 1")
        with pytest.raises(httpx.RemoteProtocolError):
            db.query(language="sql", command="HANGUP")
        assert srv._transport is not None
        assert srv._transport.stale_retries == 1
    assert fake.commands() == ["SELECT 1", "HANGUP", "HANGUP"]  # sent twice and no more


def test_a_failure_after_the_headers_were_read_is_not_retried(fake: FakeArcadeDB, transport: TransportName) -> None:
    with connect(fake, transport) as srv:
        db = srv.db("d")
        db.query(language="sql", command="SELECT 1")
        with pytest.raises(httpx.RemoteProtocolError):
            db.query(language="sql", command="PARTIAL")
        assert db.query(language="sql", command="SELECT 2").result[0]["echo"] == "SELECT 2"
    assert fake.commands() == ["SELECT 1", "PARTIAL", "SELECT 2"]


def test_a_read_timeout_raises_httpx_read_timeout_and_the_connection_is_not_reused(
    fake: FakeArcadeDB, transport: TransportName
) -> None:
    with connect(fake, transport, timeout=httpx.Timeout(0.2)) as srv:
        db = srv.db("d")
        with pytest.raises(httpx.ReadTimeout):
            db.query(language="sql", command="SLOW")
        assert db.query(language="sql", command="after").result[0]["echo"] == "after"  # not the late answer to SLOW
    assert fake.accepted == 2


def test_a_per_call_timeout_replaces_the_clients(fake: FakeArcadeDB) -> None:
    fake.delay = 0.4
    with connect(fake, "http.client", timeout=httpx.Timeout(10.0)) as srv:
        transport = srv._transport
        assert transport is not None
        db = srv.db("d")
        path = f"/api/v1/command/{db.name}"
        headers = transport.headers_for({"Content-Type": "application/json"})
        body = encode_json({"command": "SLOW", "language": "sql"})
        with pytest.raises(httpx.ReadTimeout):
            transport.request("POST", path, headers, body, timeout=0.1)
        with pytest.raises(httpx.ReadTimeout):
            transport.request("POST", path, headers, body, timeout=httpx.Timeout(connect=5, read=0.1, write=5, pool=5))
        assert transport.request("POST", path, headers, body, timeout=None).status == 200  # None: no timeout
        assert transport.request("POST", path, headers, encode_json({"command": "x", "language": "sql"})).status == 200


def test_a_refused_connection_raises_httpx_connect_error(transport: TransportName) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with (
        ArcadeDBServer(base_url=f"http://127.0.0.1:{port}", transport=transport) as srv,
        pytest.raises(httpx.ConnectError),
    ):
        srv.db("d").query(language="sql", command="SELECT 1")


def _hammer(db: ArcadeDBDatabase, thread: int, calls: int, wrong: list[str], start: threading.Barrier) -> None:
    start.wait(timeout=10)
    for i in range(calls):
        command = f"t{thread}-{i}"
        answer = db.query(language="sql", command=command, params={"thread": thread})
        if answer.result != [{"echo": command, "params": {"thread": thread}, "language": "sql"}]:
            wrong.append(f"{command}: {answer.result}")


@pytest.mark.parametrize("shared_handle", [False, True])
def test_eight_threads_each_get_their_own_answers(
    fake: FakeArcadeDB, transport: TransportName, shared_handle: bool
) -> None:
    threads, calls = 8, 25
    wrong: list[str] = []
    start = threading.Barrier(threads)
    with connect(fake, transport) as srv:
        shared = srv.db("d")
        workers = [
            threading.Thread(target=_hammer, args=(shared if shared_handle else srv.db("d"), n, calls, wrong, start))
            for n in range(threads)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=30)
    assert wrong == []
    assert len(fake.commands()) == threads * calls
    assert len(set(fake.commands())) == threads * calls
    assert fake.accepted <= threads  # a thread uses one connection at a time, and reuses it


def test_a_gzip_answer_is_decoded_like_httpx_decodes_it(fake: FakeArcadeDB, transport: TransportName) -> None:
    fake.gzip_answers = True
    with connect(fake, transport) as srv:
        db = srv.db("d")
        assert db.query(language="sql", command="ROWS:200").returned == 200
        with pytest.raises(ArcadeDBError) as caught:
            db.query(language="sql", command="ERR:500")
    assert (caught.value.status, caught.value.detail, caught.value.request_id) == (500, "line 1", "req-1")


def test_streams_and_other_calls_stay_on_httpx(fake: FakeArcadeDB) -> None:
    with connect(fake, "http.client") as srv:
        db = srv.db("d")
        db.query(language="sql", command="SELECT 1")
        events = list(db.query_stream(language="sql", command="SELECT 2"))
        assert srv.ready() is True
    assert len(events) == 3
    agents = [s.headers["user-agent"] for s in fake.seen]
    assert agents[0] == "arcadedb-driver"
    assert agents[1].startswith("python-httpx/")
    assert agents[2].startswith("python-httpx/")


def test_with_token_keeps_the_transport(fake: FakeArcadeDB) -> None:
    with connect(fake, "http.client") as srv, srv.with_token("tok-1") as other:
        other.db("d").query(language="sql", command="SELECT 1")
    assert fake.seen[0].headers["authorization"] == "Bearer tok-1"
    assert fake.seen[0].headers["user-agent"] == "arcadedb-driver"


def test_a_closed_server_refuses_calls_as_httpx_does(fake: FakeArcadeDB, transport: TransportName) -> None:
    srv = connect(fake, transport)
    db = srv.db("d")
    db.query(language="sql", command="SELECT 1")
    srv.close()
    with pytest.raises(RuntimeError, match="closed"):
        db.query(language="sql", command="SELECT 2")


def test_a_connection_put_back_while_close_runs_is_not_left_open(fake: FakeArcadeDB) -> None:
    """`close()` can run between a call's check of the closed flag and its putting its connection back.

    The call has its answer by then and returns normally, but its connection must not stay idle in a
    pool that `close()` has already drained.
    """
    srv = connect(fake, "http.client")
    assert srv._transport is not None
    transport: HttpClientTransport = srv._transport

    class CloseBeforeAppend(deque[_Slot]):
        def append(self, slot: _Slot) -> None:
            transport.close()
            super().append(slot)

    transport._idle = CloseBeforeAppend()
    assert srv.db("d").query(language="sql", command="SELECT 1").returned == 1
    assert len(transport._idle) == 0
    srv.close()


def test_an_unknown_transport_is_refused() -> None:
    with pytest.raises(ValueError, match="unsupported transport"):
        ArcadeDBServer(base_url="http://db.test", transport="requests")  # type: ignore[arg-type]


@pytest.mark.parametrize("base_url", ["ftp://db.test", "db.test:2480", "http://"])
def test_http_client_needs_an_http_or_https_url_with_a_host(base_url: str) -> None:
    with pytest.raises(ValueError, match="http:// or https://"):
        ArcadeDBServer(base_url=base_url, transport="http.client")


def test_an_https_base_url_opens_a_tls_connection() -> None:
    # Only the connection class and its address are checked here; no TLS handshake is made.
    transport = HttpClientTransport(base_url="https://db.test:2490/arcade", headers={}, verify_ssl=False)
    conn = transport._new_slot().conn
    assert isinstance(conn, http.client.HTTPSConnection)
    assert (conn.host, conn.port, transport.prefix) == ("db.test", 2490, "/arcade")
    plain = HttpClientTransport(base_url="http://db.test", headers={})._new_slot().conn
    assert not isinstance(plain, http.client.HTTPSConnection)
    assert (plain.host, plain.port) == ("db.test", 80)
