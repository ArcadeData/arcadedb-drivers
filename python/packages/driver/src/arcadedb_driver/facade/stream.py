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
  started, which is why the contract carries it in band at all instead of as an HTTP status. The
  raised error's status is 200: honest, and no different from what M4 already established for
  `ArcadeDBError`. Raising here means the streaming and buffered paths fail exactly the same way.
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
otherwise healthy stream instead of an `ArcadeDBError`. `_iter_ndjson_lines` below splits on `"\\n"`
and nothing else, carrying a `remainder` across chunks, which is exactly what `facade/stream.ts`'s
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
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from typing import Any
from urllib.parse import quote

import httpx

from .._generated.client import Client
from .._generated.models.nd_json_query_event import NdJsonQueryEvent
from .._generated.types import Unset
from ..errors import REQUEST_ID_HEADER, ArcadeDBError
from .data import SESSION_HEADER, QueryLanguage, build_command_request, build_query_request


def _query_url(database: str) -> str:
    return f"/api/v1/query/{quote(database, safe='')}"


def _command_url(database: str) -> str:
    return f"/api/v1/command/{quote(database, safe='')}"


def _headers(session_id: str | None) -> dict[str, str]:
    headers = {"Accept": "application/x-ndjson"}
    if session_id is not None:
        headers[SESSION_HEADER] = session_id
    return headers


def _parse_event(line: str) -> NdJsonQueryEvent:
    """Parses one ndjson line, raising `ArcadeDBError` if it is an in-band `error` event rather
    than returning it - see the module docstring for why 200 is the right status to carry."""
    event = NdJsonQueryEvent.from_dict(json.loads(line))
    if not isinstance(event.error, Unset):
        message = event.error.message
        detail = "the stream reported an error" if isinstance(message, Unset) else message
        raise ArcadeDBError(200, {"error": detail})
    return event


def _raise_for_status(response: httpx.Response) -> None:
    """Raises `ArcadeDBError` unless the server answered 2xx.

    Reads the body first: a streaming response has not been read yet, and `ArcadeDBError` needs
    the body for the server's detail.
    """
    if not response.is_success:
        response.read()
        raise ArcadeDBError(response.status_code, response.content, response.headers.get(REQUEST_ID_HEADER))


async def _araise_for_status(response: httpx.Response) -> None:
    """The async twin of `_raise_for_status`."""
    if not response.is_success:
        await response.aread()
        raise ArcadeDBError(response.status_code, response.content, response.headers.get(REQUEST_ID_HEADER))


def _iter_ndjson_lines(chunks: Iterator[str]) -> Iterator[str]:
    """Splits already-decoded text chunks into ndjson lines on `"\\n"` and nothing else.

    See the module docstring for why `iter_lines()` cannot be used for this. A `remainder` carries
    whatever the last chunk left unterminated into the next one, and is emitted after the stream
    ends so a final line with no trailing newline is not dropped.
    """
    remainder = ""
    for chunk in chunks:
        remainder += chunk
        *lines, remainder = remainder.split("\n")
        yield from lines
    if remainder:
        yield remainder


async def _aiter_ndjson_lines(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """The async twin of `_iter_ndjson_lines`."""
    remainder = ""
    async for chunk in chunks:
        remainder += chunk
        *lines, remainder = remainder.split("\n")
        for line in lines:
            yield line
    if remainder:
        yield remainder


def _stream_events(
    client: Client, url: str, body: dict[str, Any], session_id: str | None
) -> Generator[NdJsonQueryEvent, None, None]:
    with client.get_httpx_client().stream("POST", url, json=body, headers=_headers(session_id)) as response:
        _raise_for_status(response)
        for line in _iter_ndjson_lines(response.iter_text()):
            if not line.strip():
                continue
            yield _parse_event(line)


async def _astream_events(
    client: Client, url: str, body: dict[str, Any], session_id: str | None
) -> AsyncGenerator[NdJsonQueryEvent, None]:
    async with client.get_async_httpx_client().stream("POST", url, json=body, headers=_headers(session_id)) as response:
        await _araise_for_status(response)
        async for line in _aiter_ndjson_lines(response.aiter_text()):
            if not line.strip():
                continue
            yield _parse_event(line)


def stream_query(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
    limit: int | None = None,
) -> Generator[NdJsonQueryEvent, None, None]:
    """Streams `POST /api/v1/query/{database}` as `application/x-ndjson`, one event per line - see
    the module docstring for what an event carries and why an in-band `error` raises."""
    body = build_query_request(language=language, command=command, params=params, limit=limit).to_dict()
    return _stream_events(client, _query_url(database), body, session_id)


def stream_command(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
) -> Generator[NdJsonQueryEvent, None, None]:
    """Streams `POST /api/v1/command/{database}` as `application/x-ndjson`, one event per line -
    see the module docstring for what an event carries and why an in-band `error` raises. Only a
    read-only statement can stream; see `ArcadeDBDatabase.command_stream`'s docstring for why a
    mutating one is refused."""
    body = build_command_request(language=language, command=command, params=params).to_dict()
    return _stream_events(client, _command_url(database), body, session_id)


def astream_query(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
    limit: int | None = None,
) -> AsyncGenerator[NdJsonQueryEvent, None]:
    """The async twin of `stream_query`."""
    body = build_query_request(language=language, command=command, params=params, limit=limit).to_dict()
    return _astream_events(client, _query_url(database), body, session_id)


def astream_command(
    client: Client,
    database: str,
    session_id: str | None,
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None = None,
) -> AsyncGenerator[NdJsonQueryEvent, None]:
    """The async twin of `stream_command`."""
    body = build_command_request(language=language, command=command, params=params).to_dict()
    return _astream_events(client, _command_url(database), body, session_id)
