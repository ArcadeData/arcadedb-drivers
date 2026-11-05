"""Running work: list and terminate queries and transactions (issue #124).

The pure half of `ArcadeDBServer`'s and `AsyncArcadeDBServer`'s `list_queries`,
`terminate_query`, `terminate_queries_by_tag`, `list_transactions` and `terminate_transaction`:
the public result types, command building, local validation and response shaping, shared so the
sync and async facades cannot drift. The methods themselves, and their full docstrings, live on
the two server classes.

Every one of them is a command string sent through `POST /api/v1/server`, posted through the
pooled httpx client for the reason `facade/admin.py` gives, and with a `wait` the contract's
`CommandRequest` does not declare although the server reads it. The answers are not in the
contract at all (it declares `QueryResponse` for every server command), so their shapes here are
the ones a 26.11.1-SNAPSHOT server sends, pinned by `e2e/test_running.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx

from ..errors import ArcadeDBError

#: What a terminate command answers for one statement or transaction. `"terminated"`: it
#: stopped and what it wrote was rolled back. `"completed"`: it ended on its own before it
#: noticed, so what it did stands. `"terminating"`: not stopped yet within the wait.
#: `"not found"`: no such statement on this server, or another user's.
QueryStatus = Literal["terminated", "completed", "terminating", "not found"]

#: The exception the server names in the 409 a terminated request receives. The status alone is
#: shared with a request still in flight under the same X-Request-Id.
QUERY_TERMINATED_EXCEPTION = "com.arcadedb.exception.QueryTerminatedException"

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RunningQuery:
    """One statement as `list_queries` returns it.

    `session_id` is `None` for a statement that does not run inside a transaction, and `tag` is
    `None` for one sent without a `query_tag`. `started_at` is timezone-aware, in UTC, and
    `elapsed` is the running time the server measured when it answered.
    """

    id: str
    database: str
    user: str
    protocol: str
    language: str
    text: str
    started_at: datetime
    elapsed: timedelta
    terminating: bool
    session_id: str | None
    tag: str | None
    client_address: str | None
    server: str


@dataclass(frozen=True)
class TerminateResult:
    """The answer for one statement or transaction.

    `session_id` and `session_open` are set only for a statement that ran inside a transaction: a
    command terminated there ends the transaction too (`session_open` False), a terminated read
    leaves it open. For a `"terminating"` statement `session_open` is only the state at the time
    of the answer, since a command ends its session as it stops.
    """

    id: str
    status: QueryStatus
    session_id: str | None = None
    session_open: bool | None = None


@dataclass(frozen=True)
class OpenTransaction:
    """One transaction session as `list_transactions` returns it. `running_queries` holds the ids
    of the statements running in it, which `terminate_query` takes."""

    id: str
    user: str
    database: str
    idle: timedelta
    busy: bool
    running_queries: list[str]
    server: str


def is_query_terminated(error: BaseException) -> bool:
    """Whether `error` is the answer to a request that `terminate_query`,
    `terminate_queries_by_tag` or `terminate_transaction` stopped.

    True for an `ArcadeDBError` with status 409 whose `exception` is
    `com.arcadedb.exception.QueryTerminatedException`, a structured field the server sends. The
    409 alone is not enough: a request still in flight under the same `X-Request-Id` gets one too.
    Not retryable: somebody stopped this work on purpose, and what it wrote was rolled back.
    """
    return isinstance(error, ArcadeDBError) and error.status == 409 and error.exception == QUERY_TERMINATED_EXCEPTION


def _space_or_control(c: str) -> bool:
    """What the server, in Java, trims and splits on: every character at or below U+0020. Not
    `str.isspace`, which would refuse a no-break space the server keeps. The Go and TypeScript
    clients use the same rule."""
    return c <= " "


def check_word(what: str, value: str) -> None:
    """Raises `ValueError` for a value the server would split: it reads a database name, a query
    id and a session id as one word."""
    if not value or any(_space_or_control(c) for c in value):
        raise ValueError(f"{what} {value!r} is empty or contains a space or control character")


def check_tag(tag: str) -> None:
    """Raises `ValueError` for a tag the server would silently change: it takes the rest of the
    command as the tag, trimmed, so " a" would match "a" rather than the tag named."""
    if tag and (_space_or_control(tag[0]) or _space_or_control(tag[-1])):
        raise ValueError(f"tag {tag!r} starts or ends with a space or control character")


def list_queries_command(database: str | None, tag: str | None) -> str:
    command = "list queries"
    if database:
        check_word("database name", database)
        command += f" database {database}"
    if tag:
        check_tag(tag)
        command += f" tag {tag}"
    return command


def terminate_query_command(query_id: str) -> str:
    check_word("query id", query_id)
    return f"terminate query {query_id}"


def terminate_by_tag_command(tag: str) -> str:
    if not tag:
        raise ValueError("tag is empty")
    check_tag(tag)
    return f"terminate queries tag {tag}"


def terminate_transaction_command(session_id: str) -> str:
    check_word("session id", session_id)
    return f"terminate transaction {session_id}"


def running_payload(command: str, wait: timedelta | None = None) -> dict[str, Any]:
    """The `POST /api/v1/server` body, with `wait` in whole milliseconds when it is positive. A
    positive wait under a millisecond is rounded up rather than sent as 0, which the server reads
    as "do not wait"."""
    payload: dict[str, Any] = {"command": command, "language": "sql"}
    if wait is not None and wait > timedelta(0):
        payload["wait"] = max(1, math.ceil(wait / timedelta(milliseconds=1)))
    return payload


def running_result(raw: httpx.Response) -> Any:
    """Raises `ArcadeDBError` unless the server answered 2xx; otherwise returns the body's
    `result`. A 2xx body with no `result` raises `ValueError`, rather than reading as an empty
    answer."""
    if not 200 <= raw.status_code < 300:
        raise ArcadeDBError.from_httpx_response(raw)
    body = raw.json() if raw.content.strip() else None
    if not isinstance(body, dict) or body.get("result") is None:
        raise ValueError(f"POST /api/v1/server answered {raw.status_code} with no result")
    return body["result"]


def _ms(value: Any) -> timedelta:
    return timedelta(milliseconds=int(value))


def running_query_from(row: dict[str, Any]) -> RunningQuery:
    return RunningQuery(
        id=row["id"],
        database=row["database"],
        user=row["user"],
        protocol=row["protocol"],
        language=row["language"],
        text=row["text"],
        started_at=_EPOCH + _ms(row["startedAt"]),
        elapsed=_ms(row["elapsedMs"]),
        terminating=bool(row["terminating"]),
        session_id=row.get("sessionId"),
        tag=row.get("tag"),
        client_address=row.get("clientAddress"),
        server=row["server"],
    )


def terminate_result_from(row: dict[str, Any]) -> TerminateResult:
    session_open = row.get("sessionOpen")
    return TerminateResult(
        id=row["id"],
        status=row["status"],
        session_id=row.get("sessionId"),
        session_open=None if session_open is None else bool(session_open),
    )


def open_transaction_from(row: dict[str, Any]) -> OpenTransaction:
    return OpenTransaction(
        id=row["id"],
        user=row["user"],
        database=row["database"],
        idle=_ms(row["idleMs"]),
        busy=bool(row["busy"]),
        running_queries=list(row.get("runningQueries") or []),
        server=row["server"],
    )
