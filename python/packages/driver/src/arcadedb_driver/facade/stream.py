"""The `query_stream` / `command_stream` pair: `/query` and `/command` as `application/x-ndjson`.

HAND-WRITTEN, unlike `query`/`command`: every generated operation (`execute_query_post.py`,
`execute_command.py`) calls `response.json()` inside its own `_parse_response` - there is no
generated call this could ride even for the plain buffered body, let alone a streamed one. What is
NOT hand-written is the transport: both the sync and async functions below reach for the generated
`Client`'s own pooled `httpx.Client` / `httpx.AsyncClient` via `.stream()` - the same escape hatch
`facade/timeseries.py`'s hand-written `write` already uses - so the base URL, auth headers and
timeout come along for free instead of being reconstructed. A second transport is exactly what
this milestone was designed to avoid; there is only one here to drift.

Three decisions, matching `queryStream`/`commandStream` in `@arcadedb/driver`:

- **Events, not rows.** Each ndjson line is one `NdJsonQueryEvent`, carrying exactly one of
  `record`, `stats` or `error`. Yielding only `record` would discard the `stats` trailer - which
  carries the same `limit`/`returned`/`truncated` `QueryEnvelope` reports at top level for the
  buffered path - and the in-band `error`. A caller who iterates rows and ignores the trailer
  cannot tell a complete result from a truncated one; that is the same hazard `QueryEnvelope`'s own
  docstring names for `query`/`command`. The generated `NdJsonQueryEvent` model is returned
  unaltered rather than normalised into a bespoke type, the same choice `facade/dashboards.py`'s
  `db.promql` and `facade/vector.py` make for their own generated responses.
- **An in-band `error` raises `ArcadeDBError`.** It is a failure the server can only report after
  the 200 status line was already sent - the status line cannot be taken back once the stream has
  started, which is why the contract carries it in band at all instead of as an HTTP status.
  Raising here means the streaming and buffered paths fail exactly the same way, field for field:
  `status` is the event's own `status` - the one the buffered encoding would have answered the same
  failure with (503 for a retryable conflict, 409 for a duplicated key, 413 for the row cap, ...) -
  falling back to 200 only when the event carries none; `error` is the classified label
  (`message` when the event has no `error`); `exception`, `detail`, `exception_args` and
  `retry_after` are copied across; and `request_id` prefers the response's `X-Request-Id` header
  over the event's own `requestId`. `commit_index` is never set from this event, which carries
  none. **Breaking change (issue #117):** the raised status used to be 200 unconditionally (D-M7-3),
  a rule chosen when the event carried no `status`. The contract now says to key retries on it, the
  batch stream already used its in-band status, and a `retry_after` beside a 200 would be
  unreadable. The event is read from the raw JSON rather than through the generated
  `NdJsonQueryEventError`, whose `from_dict` treats `status` and `message` as required and would
  raise `KeyError` - not `ArcadeDBError` - on an older server's event that lacks either.
- **`query`/`command` are untouched.** They keep returning `QueryEnvelope` and keep sending no
  `Accept` header at all; streaming is a separate pair of methods, not a mode of the existing two.

Two more things, the first of which both clients must solve and each solves in its own idiom:

1. **Closing the connection on early abandonment.** `httpx`'s `.stream()` is a context manager
   whose `finally` calls `response.close()` - but a generator that `yield`s from inside that block
   does not run that `finally` until the generator itself is finalised, whether by exhaustion, an
   explicit `close()`/`aclose()`, or garbage collection. Nothing extra needs writing for this
   correctly, though: the `with`/`async with` lives directly in the generator body below, so a
   `GeneratorExit` thrown into the suspended `yield` (which is what `.close()`/`.aclose()` and
   `for ... break` both eventually do) propagates out through the block exactly like any other
   exception, and the context manager's `__exit__`/`__aexit__` runs during that unwind - see
   `test_stream.py`'s explicit `.close()`/`.aclose()` tests, modelled on
   `arcadedb-driver-grpc`'s. This is the same class of hazard M6 named for a plain Python `for`
   loop that never closes the iterable it consumes on early exit; the fix here is structural
   rather than an explicit `try`/`finally`, because the iterable being closed is this function's
   own local `with` block, not a caller-supplied one. `facade/stream.ts` faces the same hazard and
   pays for it explicitly - releasing its reader's lock does not cancel the response body, so its
   `finally` calls `reader.cancel()`. What differs is the idiom, not the requirement.
2. **Reading a non-2xx body before it can be reported.** A streaming response's body has not been
   read when its status line arrives - accessing `.content` before `.read()`/`.aread()` raises
   `httpx.ResponseNotRead`. `ArcadeDBError` needs that body for the server's error detail, so it is
   read explicitly, exactly once, before `ArcadeDBError` is raised.

**The line splitting is hand-rolled, deliberately, and must stay that way.**
`httpx.Response.iter_lines()` / `.aiter_lines()` do buffer a partial line across chunk boundaries,
which is why they look like the obvious thing to use here - but they split on `str.splitlines()`
semantics, and that is a strictly larger set of line terminators than ndjson has. Besides `\\n` and
`\\r`, `splitlines()` breaks on U+0085, U+2028 and U+2029, and all three are *legal raw characters
inside a JSON string*: the JSON grammar requires escaping only `"`, `\\` and the C0 controls, and
Jackson (the server's serialiser) emits them raw. So one record carrying any of the three - scraped
web text, JavaScript-sourced content, Windows-1252 mojibake that decodes to U+0085 - is cut in half
mid-string by `iter_lines()`, and the caller gets a bare `json.JSONDecodeError` partway through an
otherwise healthy stream instead of an `ArcadeDBError`. `iter_ndjson_lines` (in
`_internal/ndjson.py`, alongside `raise_for_status`/`araise_for_status`) splits on `"\\n"` and
nothing else, carrying a `remainder` across chunks, which is exactly what `facade/stream.ts`'s
decoder does; the two languages now agree line for line. `test_stream.py` asserts both the
split-line case and the U+2028 case, sync and async - the second is the regression this hand-rolled
loop exists to prevent, so anyone tempted to "simplify" it back to `iter_lines()` meets a red test.

The encoding half of the same problem is *not* hand-rolled: `iter_text()` / `aiter_text()` run the
body through an incremental codec, so a multi-byte UTF-8 sequence straddling a chunk boundary is
held back and completed rather than turned into U+FFFD. That is the same hazard `facade/stream.ts`
must spend a `TextDecoder(..., { stream: true })` on by hand; here httpx supplies it, so these
functions take `str` chunks and never touch bytes.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator
from typing import Any
from urllib.parse import quote

from .._generated.client import Client
from .._generated.models.nd_json_query_event import NdJsonQueryEvent
from .._internal.ndjson import aiter_ndjson_lines, araise_for_status, iter_ndjson_lines, raise_for_status
from ..errors import REQUEST_ID_HEADER, ArcadeDBError, _int_or_none, _str_or_none
from .data import SESSION_HEADER, QueryLanguage, build_command_request, build_query_request, query_tag_headers


def _query_url(database: str) -> str:
    return f"/api/v1/query/{quote(database, safe='')}"


def _command_url(database: str) -> str:
    return f"/api/v1/command/{quote(database, safe='')}"


def _headers(session_id: str | None, query_tag: str | None) -> dict[str, str]:
    headers = {"Accept": "application/x-ndjson", **query_tag_headers(query_tag)}
    if session_id is not None:
        headers[SESSION_HEADER] = session_id
    return headers


def _in_band_error(error: dict[str, Any], header_request_id: str | None) -> ArcadeDBError:
    """Maps an in-band `error` object onto `ArcadeDBError` - see the module docstring for the
    field mapping and why `status` falls back to 200 only when the event carries none."""
    status = error.get("status")
    label = _str_or_none(error.get("error")) or _str_or_none(error.get("message")) or "the stream reported an error"
    body: dict[str, Any] = {"error": label}
    for key in ("exception", "detail", "exceptionArgs", "requestId"):
        value = _str_or_none(error.get(key))
        if value is not None:
            body[key] = value
    return ArcadeDBError(
        status if isinstance(status, int) and not isinstance(status, bool) else 200,
        body,
        header_request_id,
        retry_after=_int_or_none(error.get("retryAfter")),
    )


def _parse_event(line: str, header_request_id: str | None) -> NdJsonQueryEvent:
    """Parses one ndjson line, raising `ArcadeDBError` if it is an in-band `error` event rather
    than returning it."""
    raw = json.loads(line)
    error = raw.get("error") if isinstance(raw, dict) else None
    if isinstance(error, dict):
        raise _in_band_error(error, header_request_id)
    return NdJsonQueryEvent.from_dict(raw)


def _stream_events(
    client: Client, url: str, body: dict[str, Any], session_id: str | None, query_tag: str | None
) -> Generator[NdJsonQueryEvent, None, None]:
    headers = _headers(session_id, query_tag)
    with client.get_httpx_client().stream("POST", url, json=body, headers=headers) as response:
        raise_for_status(response)
        request_id = response.headers.get(REQUEST_ID_HEADER)
        for line in iter_ndjson_lines(response.iter_text()):
            if not line.strip():
                continue
            yield _parse_event(line, request_id)


async def _astream_events(
    client: Client, url: str, body: dict[str, Any], session_id: str | None, query_tag: str | None
) -> AsyncGenerator[NdJsonQueryEvent, None]:
    headers = _headers(session_id, query_tag)
    async with client.get_async_httpx_client().stream("POST", url, json=body, headers=headers) as response:
        await araise_for_status(response)
        request_id = response.headers.get(REQUEST_ID_HEADER)
        async for line in aiter_ndjson_lines(response.aiter_text()):
            if not line.strip():
                continue
            yield _parse_event(line, request_id)


def stream_query(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
    limit: int | None = None,
    query_tag: str | None = None,
) -> Generator[NdJsonQueryEvent, None, None]:
    """Streams `POST /api/v1/query/{database}` as `application/x-ndjson`, one event per line - see
    the module docstring for what an event carries and why an in-band `error` raises."""
    body = build_query_request(language=language, command=command, params=params, limit=limit).to_dict()
    return _stream_events(client, _query_url(database), body, session_id, query_tag)


def stream_command(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
    query_tag: str | None = None,
) -> Generator[NdJsonQueryEvent, None, None]:
    """Streams `POST /api/v1/command/{database}` as `application/x-ndjson`, one event per line -
    see the module docstring for what an event carries and why an in-band `error` raises. Only a
    read-only statement can stream; see `ArcadeDBDatabase.command_stream`'s docstring for why a
    mutating one is refused."""
    body = build_command_request(language=language, command=command, params=params).to_dict()
    return _stream_events(client, _command_url(database), body, session_id, query_tag)


def astream_query(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
    limit: int | None = None,
    query_tag: str | None = None,
) -> AsyncGenerator[NdJsonQueryEvent, None]:
    """The async twin of `stream_query`."""
    body = build_query_request(language=language, command=command, params=params, limit=limit).to_dict()
    return _astream_events(client, _query_url(database), body, session_id, query_tag)


def astream_command(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
    query_tag: str | None = None,
) -> AsyncGenerator[NdJsonQueryEvent, None]:
    """The async twin of `stream_command`."""
    body = build_command_request(language=language, command=command, params=params).to_dict()
    return _astream_events(client, _command_url(database), body, session_id, query_tag)
