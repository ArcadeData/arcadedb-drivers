"""The facade's error type.

`ArcadeDBServer.raw` - the generated client - never raises this, or anything
else: it returns a `Response` whose `status_code` the caller inspects. That
asymmetry is deliberate and mirrors `@arcadedb/driver`, where `raw` returns
`{ data, error }` while every facade method throws.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
from typing_extensions import Self

from ._generated.models.error_response import ErrorResponse
from ._generated.types import Response

#: The server sets this on every response, generating a value when the client sent
#: none, so it is a usable correlation id unconditionally - not only when the caller
#: supplied its own.
REQUEST_ID_HEADER = "X-Request-Id"

#: Seconds to wait before retrying. The server sends it on a refusal that carries a
#: back-off: 503 when the node cannot execute the request yet (a snapshot install, a
#: leader change), 409 when an identical request is still in flight.
RETRY_AFTER_HEADER = "Retry-After"

#: The Raft commit index the response was produced at. Sent on errors too, and still a
#: valid read-after barrier there; absent on a standalone (non-HA) database.
COMMIT_INDEX_HEADER = "X-ArcadeDB-Commit-Index"


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def parse_header_int(value: str | None) -> int | None:
    """Parses a header value as a non-negative base-10 integer, or returns `None`.

    Surrounding whitespace is trimmed; anything else - an HTTP-date `Retry-After`, a sign, a
    decimal point, a non-ASCII digit, an empty value - yields `None` rather than raising, because
    this runs on the failure path and an error type that can itself fail turns a server error into
    a confusing client-side crash. `str.isdigit()` alone is not enough: it accepts digits from
    every script (and superscripts), which `int()` would then parse or reject inconsistently.
    """
    if value is None:
        return None
    text = value.strip()
    if not text or not text.isascii() or not text.isdigit():
        return None
    return int(text)


def _int_or_none(value: object) -> int | None:
    """A JSON number that is a non-negative integer, else `None`. `bool` is excluded: in Python
    it is an `int`, but `true` is never a count or a number of seconds."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Reads one header case-insensitively from any mapping: an `httpx.Headers` already is, but
    the generated `Response.headers` is typed as a plain mapping."""
    value = headers.get(name)
    if value is not None:
        return value
    wanted = name.lower()
    for key, candidate in headers.items():
        if key.lower() == wanted:
            return candidate
    return None


def _header_fields(headers: Mapping[str, str]) -> dict[str, Any]:
    """The `ArcadeDBError` keyword arguments a non-2xx response's headers contribute."""
    return {
        "request_id": _header(headers, REQUEST_ID_HEADER),
        "retry_after": parse_header_int(_header(headers, RETRY_AFTER_HEADER)),
        "commit_index": parse_header_int(_header(headers, COMMIT_INDEX_HEADER)),
    }


def _parse_body(body: object) -> dict[str, Any]:
    """Reduces whatever the server sent to a dict, never raising.

    The server guarantees none of these fields, and the body may be absent, empty,
    or not JSON at all. A body that is not a JSON object yields an empty dict, so
    the resulting error carries nothing beyond its HTTP status.
    """
    if isinstance(body, bytes):
        try:
            body = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return {}
    if isinstance(body, ErrorResponse):
        body = body.to_dict()
    return body if isinstance(body, dict) else {}


class ArcadeDBError(Exception):
    """Raised by every facade method when the server answers with a non-2xx status.

    Carries the HTTP status plus whatever the server's JSON error body contributed.
    Every field beyond `status` is optional, because the body may be absent,
    unparsable, or missing individual fields.

    Two fields come from the response's headers rather than its body:

    - `retry_after`: seconds to wait before retrying, from `Retry-After` - `None` when
      the header is absent or is not a plain non-negative integer (an HTTP-date form is
      not parsed). An in-band streaming error carries it in the event instead, since a
      header cannot be added once the stream has started.
    - `commit_index`: the Raft commit index, from `X-ArcadeDB-Commit-Index` (or a batch
      stream's in-band `commitIndex`). It is still a valid read-after barrier on an
      error: feed it back as `X-ArcadeDB-Read-After` to read at least that state. `None`
      on a standalone database, which sends no such header.

    A 409 has two meanings, and `status` alone cannot tell them apart: "an identical
    request is still in flight" (retryable - `exception` is
    `RequestStillInFlightException` and `retry_after` is set) and "the query was
    terminated" by `terminate query/queries/transaction` (writes rolled back - NOT
    retryable). This client retries neither; retry logic must key on `exception` /
    `retry_after`, never on the status alone.
    """

    def __init__(
        self,
        status: int,
        body: object = None,
        request_id: str | None = None,
        *,
        retry_after: int | None = None,
        commit_index: int | None = None,
    ) -> None:
        parsed = _parse_body(body)
        self.status = int(status)
        self.error = _str_or_none(parsed.get("error"))
        self.exception = _str_or_none(parsed.get("exception"))
        self.detail = _str_or_none(parsed.get("detail"))
        self.request_id = request_id or _str_or_none(parsed.get("requestId"))
        # Spelled `help_` to match the generated ErrorResponse model, which is
        # reachable through `.raw`. One awkward name beats two spellings of one
        # field inside a package that exposes both.
        self.help_ = _str_or_none(parsed.get("help"))
        # Despite the plural name the contract types this as a plain string, not an
        # array. Passed through as-is rather than parsed or coerced.
        self.exception_args = _str_or_none(parsed.get("exceptionArgs"))
        self.retry_after = retry_after
        self.commit_index = commit_index
        super().__init__(self.error or self.detail or f"ArcadeDB request failed with status {self.status}")

    @classmethod
    def from_response(cls, response: Response[Any]) -> Self:
        """Builds an error from a generated `Response`.

        Prefers the already-parsed `ErrorResponse` when the contract documented one
        for this status, and falls back to re-reading the raw bytes when it did not.
        `request_id`, `retry_after` and `commit_index` come from the headers.
        """
        body: object = response.parsed if isinstance(response.parsed, ErrorResponse) else response.content
        return cls(int(response.status_code), body, **_header_fields(response.headers))

    @classmethod
    def from_httpx_response(cls, response: httpx.Response) -> Self:
        """Builds an error from a raw `httpx.Response`, the shape every hand-written call
        (`ts`, `grafana`, `batch_load`, the streaming endpoints) receives. The body must
        already have been read. `request_id`, `retry_after` and `commit_index` come from
        the headers.
        """
        return cls(response.status_code, response.content, **_header_fields(response.headers))


def _str_list(value: object) -> list[str]:
    """The string elements of a JSON array; an empty list for anything that is not an array."""
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


class TimeSeriesWriteError(ArcadeDBError):
    """Raised by `db.ts.write` when the server answers 400 with a JSON object body.

    A subclass of `ArcadeDBError`, so `except ArcadeDBError` still catches it, and every
    `ArcadeDBError` field (`status`, `error`, `request_id`, `retry_after`, `commit_index`,
    ...) is filled the usual way. On top of those it carries the contract's
    `TimeSeriesWriteError` body:

    - `written` / `dropped`: how many samples landed and how many did not, `None` when the
      body omits one. **A write is not atomic**: `written` samples are durable even though
      the call raised (a rollback of a surrounding transaction does not take them back
      either), so retry the dropped measurements rather than the whole payload.
    - `unknown_types`: measurements naming a type that does not exist.
    - `non_time_series_types`: measurements naming a type that exists but is not a
      time-series type.
    - `unavailable_types`: measurements naming a time-series type whose storage engine
      failed to load (the server log says why).
    - `undeclared_keys`: `'<measurement>.<key> (tag|field)'` entries for keys the type
      does not declare in that role; the samples carrying them were dropped. Capped at
      100 entries by the server. A server set to
      `arcadedb.timeSeriesUndeclaredKeys=ignore` stores such samples with the undeclared
      keys discarded instead of dropping them.

    Each list is empty when the body omits it; a non-string element is dropped. Any other
    status - and a 400 whose body is not a JSON object - raises a plain `ArcadeDBError`.
    """

    def __init__(
        self,
        status: int,
        body: object = None,
        request_id: str | None = None,
        *,
        retry_after: int | None = None,
        commit_index: int | None = None,
    ) -> None:
        super().__init__(status, body, request_id, retry_after=retry_after, commit_index=commit_index)
        parsed = _parse_body(body)
        self.written = _int_or_none(parsed.get("written"))
        self.dropped = _int_or_none(parsed.get("dropped"))
        self.unknown_types = _str_list(parsed.get("unknownTypes"))
        self.non_time_series_types = _str_list(parsed.get("nonTimeSeriesTypes"))
        self.unavailable_types = _str_list(parsed.get("unavailableTypes"))
        self.undeclared_keys = _str_list(parsed.get("undeclaredKeys"))


class InsertSessionError(Exception):
    """Raised by a `/ws` insert session (`InsertSession` / `AsyncInsertSession`) for every failure.

    Deliberately NOT an `ArcadeDBError`: that type carries an HTTP status, and nothing here has
    one. The WebSocket handshake can fail with one (`__cause__` then holds the library's own
    exception), but a refused frame, a timeout and a dropped connection have none.

    `frame` is the server's `error` frame when the failure was one, else `None` (a timeout, a
    dropped connection and a refusal made client-side carry none). `session_id` is the session the
    failure concerns, or `None` when it was not yet known. `session_closed` says whether the
    session can still be used: `False` for a chunk the server refused whole (the session carries
    on and the chunk may be split and resent under the same sequence number), `True` for
    everything that ended it - an expired session, a timeout, a closed connection, an out-of-step
    answer.
    """

    def __init__(
        self,
        message: str,
        *,
        frame: dict[str, Any] | None = None,
        session_id: str | None = None,
        session_closed: bool = True,
    ) -> None:
        super().__init__(message)
        self.frame = frame
        self.session_id = session_id
        self.session_closed = session_closed
