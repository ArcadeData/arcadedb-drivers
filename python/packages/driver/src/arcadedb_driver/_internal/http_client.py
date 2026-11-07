"""An optional `http.client` transport for the synchronous client's JSON calls (issue #187).

`ArcadeDBServer(transport="http.client")` sends `query`, `command` and the transaction calls
(`begin`, `commit`, `rollback`) over persistent `http.client` connections instead of httpx. A call
that goes through httpx, over this transport or not, is the same request and gets the same answer:
what the transport hands back is parsed by the code the httpx path uses (`fast_envelope_from_bytes`,
then the generated `_build_response`, `unwrap` and `to_envelope`), so a non-2xx status, an `explain`
result or an odd shape raise and return what they always did.

What stays on httpx, always: `query_stream`/`command_stream`, `batch_load`/`batch_load_stream`, the
time-series, vector, dashboard, administration, session and running-work calls, `insert_session`
(a WebSocket) and `.raw`. They share the server object but not its connections.

The module is deliberately small and has no state beyond the connections:

- Connections. A call takes an idle connection (the most recently used one) or opens a new one, owns
  it until the answer is read, and puts it back. One thread therefore reuses one connection, and
  threads sharing a client each get their own, the guarantee httpx's pool gives. At most
  `MAX_IDLE_CONNECTIONS` stay open between calls (httpx's default `max_keepalive_connections`);
  `close()` closes the idle ones and every connection still in use when it comes back.
- Errors. An exception from the socket layer becomes the httpx exception httpx itself raises for the
  same failure (`ConnectError`, `ConnectTimeout`, `ReadTimeout`, `WriteTimeout`,
  `RemoteProtocolError`, ...), so `except httpx.HTTPError` keeps working whichever transport is
  chosen. A connection that failed or timed out is closed, never reused: a late answer on it would
  be read as the answer to the next call.
- Timeouts. `http.client` has one timeout per socket, where httpx has four phases. The connect
  timeout applies to the TCP (and TLS) connect, and the read timeout of an `httpx.Timeout` to every
  later send and receive; the write and pool timeouts are not separate settings here. A per-call
  timeout (`float`, `httpx.Timeout` or `None`) replaces the client's for that call.
- Not carried over: proxies (`HTTP_PROXY` and friends, which httpx reads from the environment),
  redirects (never followed, as with the httpx client the facade builds), HTTP/2 and httpx's
  `event_hooks`. Calls that need them stay on httpx.
- `Accept-Encoding: gzip, deflate` is sent, as httpx sends it, and a gzip or deflate body is decoded.
"""

from __future__ import annotations

import http.client
import json
import zlib
from collections import deque
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote, urlsplit

import httpx

from ..facade.data import request_headers

if TYPE_CHECKING:
    from httpx._client import UseClientDefault
else:
    UseClientDefault = type(httpx.USE_CLIENT_DEFAULT)

#: The transports `ArcadeDBServer(transport=...)` accepts.
TransportName = Literal["httpx", "http.client"]
TRANSPORTS: tuple[TransportName, ...] = ("httpx", "http.client")

#: A per-call timeout, as httpx takes one: seconds for every phase, an `httpx.Timeout`, `None` for no
#: timeout, or `USE_CLIENT_DEFAULT` to keep the client's own.
CallTimeout = float | httpx.Timeout | None | UseClientDefault
USE_CLIENT_DEFAULT = httpx.USE_CLIENT_DEFAULT

#: Idle connections kept open between calls; the same number httpx keeps by default.
MAX_IDLE_CONNECTIONS = 20

# What httpx sends on its own, minus what http.client adds itself (`Host`, `Content-Length`). The
# client's and the call's headers are laid over these.
_BASE_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "User-Agent": "arcadedb-driver",
}

# Byte for byte what httpx 0.28 sends for `json=`: compact separators, no ASCII escaping, no NaN.
_encode = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode

# `RemoteDisconnected` (the server closed the connection before sending a status line) is a
# `ConnectionResetError`, so this covers it. See `HttpClientTransport.request` for the retry rule.
_STALE = (BrokenPipeError, ConnectionResetError)

_NOT_SET = object()


def encode_json(body: Any) -> bytes:
    """The request body for `json=body`, as httpx would encode it."""
    return _encode(body).encode("utf-8")


def _split_timeout(timeout: float | httpx.Timeout | None) -> tuple[float | None, float | None]:
    """`(connect, io)` socket timeouts for an httpx-style timeout; see the module docstring."""
    if isinstance(timeout, httpx.Timeout):
        return timeout.connect, timeout.read
    return timeout, timeout


def _merge_headers(base: Mapping[str, str], extra: Mapping[str, str]) -> dict[str, str]:
    """`base` overlaid with `extra`, matching names case-insensitively as httpx does."""
    replaced = {name.lower() for name in extra}
    merged = {name: value for name, value in base.items() if name.lower() not in replaced}
    merged.update(extra)
    return merged


def _decode(content: bytes, encoding: str) -> bytes:
    """Undoes the `Content-Encoding` chain httpx undoes (gzip, deflate); anything else is left as sent."""
    try:
        for token in reversed([part.strip().lower() for part in encoding.split(",")]):
            if token in ("gzip", "x-gzip"):
                content = zlib.decompress(content, 16 + zlib.MAX_WBITS)
            elif token == "deflate":
                try:
                    content = zlib.decompress(content)
                except zlib.error:
                    content = zlib.decompress(content, -zlib.MAX_WBITS)
    except zlib.error as exc:
        raise httpx.DecodingError(f"could not decode the {encoding!r} response body: {exc}") from exc
    return content


class TransportResponse:
    """What came back: the status, the (decoded) body bytes and the parsed headers."""

    __slots__ = ("content", "message", "status")

    def __init__(self, status: int, content: bytes, message: http.client.HTTPMessage) -> None:
        self.status = status
        self.content = content
        self.message = message

    def as_httpx(self) -> httpx.Response:
        """The same answer as an `httpx.Response`, for the generated parsers and `ArcadeDBError`.

        Only the paths that are not the common one (an error, `explain`, a 204 with a header to read)
        call this; a plain row result never builds one. `Content-Encoding` is left out because the
        body is already decoded.
        """
        headers = [(name, value) for name, value in self.message.items() if name.lower() != "content-encoding"]
        return httpx.Response(self.status, headers=headers, content=self.content)


class _Slot:
    """One connection, the socket timeout last applied to it, and whether it has carried a call yet."""

    __slots__ = ("conn", "io_timeout", "reused")

    def __init__(self, conn: http.client.HTTPConnection) -> None:
        self.conn = conn
        self.io_timeout: Any = _NOT_SET
        self.reused = False

    def close(self) -> None:
        self.conn.close()


class DataPaths:
    """The absolute `/query/{database}` and `/command/{database}` paths of one database on one transport.

    The twin of `facade.data.DataUrls`, resolved once and rebuilt when the database name changes
    (`ArcadeDBDatabase.name` is a public attribute). The cache is one tuple replaced in a single
    assignment, so a handle shared between threads can not read a half-refreshed pair.
    """

    __slots__ = ("_cache", "_prefix")

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._cache: tuple[str | None, str, str] = (None, "", "")

    def _resolve(self, database: str) -> tuple[str | None, str, str]:
        quoted = quote(str(database), safe="")
        return (database, f"{self._prefix}/api/v1/query/{quoted}", f"{self._prefix}/api/v1/command/{quoted}")

    def query(self, database: str) -> str:
        cache = self._cache
        if cache[0] != database:
            cache = self._cache = self._resolve(database)
        return cache[1]

    def command(self, database: str) -> str:
        cache = self._cache
        if cache[0] != database:
            cache = self._cache = self._resolve(database)
        return cache[2]


class BoundTransport:
    """One `ArcadeDBDatabase` handle's view of a transport: its paths and its precomputed headers.

    Everything that does not change between calls is built here once, so a call allocates only its
    body: the headers of a call without a `query_tag` are one dict made when the handle is built.
    """

    __slots__ = ("_headers", "_paths", "_session_id", "_transport")

    def __init__(self, transport: HttpClientTransport, session_id: str | None) -> None:
        self._transport = transport
        self._session_id = session_id
        self._paths = DataPaths(transport.prefix)
        self._headers = transport.headers_for(request_headers(session_id))

    def post(
        self,
        endpoint: Literal["query", "command"],
        database: str,
        body: dict[str, Any],
        query_tag: str | None,
        timeout: CallTimeout = USE_CLIENT_DEFAULT,
    ) -> TransportResponse:
        """`POST /api/v1/{endpoint}/{database}` with `body` as JSON; `timeout` replaces the client's for this call."""
        path = self._paths.query(database) if endpoint == "query" else self._paths.command(database)
        headers = (
            self._transport.headers_for(request_headers(self._session_id, query_tag)) if query_tag else self._headers
        )
        return self._transport.request("POST", path, headers, encode_json(body), timeout)


class HttpClientTransport:
    """Persistent `http.client` connections to one server, safe to share between threads."""

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: httpx.Timeout | None = None,
        verify_ssl: bool = True,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(
                f"transport='http.client' needs an http:// or https:// base_url with a host, got {base_url!r}"
            )
        self._https = parts.scheme == "https"
        self._host = parts.hostname
        self._port = parts.port
        #: The path of `base_url` without a trailing slash, put before every request path as httpx does.
        self.prefix = parts.path.rstrip("/")
        self._context = httpx.create_ssl_context(verify=verify_ssl) if self._https else None
        self._connect_timeout, self._io_timeout = _split_timeout(timeout)
        self._headers = _merge_headers(_BASE_HEADERS, headers)
        # `deque.append` and `deque.pop` are atomic, so taking and returning a connection needs no lock.
        self._idle: deque[_Slot] = deque()
        self._closed = False
        #: How many calls were sent again on a new connection because the idle one had gone stale.
        self.stale_retries = 0

    def bind(self, session_id: str | None) -> BoundTransport:
        """The view of this transport for one database handle (`session_id` is the transaction's, if any)."""
        return BoundTransport(self, session_id)

    def headers_for(self, per_request: Mapping[str, str]) -> dict[str, str]:
        """The headers of a call: what httpx sends by default, the client's headers, then `per_request`."""
        return _merge_headers(self._headers, per_request)

    def call(self, operation: Any, client: Any, *args: Any, **kwargs: Any) -> Any:
        """Runs one generated operation over this transport and returns its generated `Response`.

        `operation` is a module under `_generated/api`: it builds the request (`_get_kwargs`) and parses
        the answer (`_build_response`) exactly as its own `sync_detailed` does over httpx, so the
        status, the parsed model and the headers are what that function would have returned.
        """
        request = operation._get_kwargs(*args, **kwargs)
        body = encode_json(request["json"]) if "json" in request else None
        response = self.request(
            str(request["method"]).upper(),
            self.prefix + request["url"],
            self.headers_for(request.get("headers", {})),
            body,
        )
        return operation._build_response(client=client, response=response.as_httpx())

    def close(self) -> None:
        """Closes the idle connections; one still in use is closed when its call returns it."""
        self._closed = True
        while self._idle:
            try:
                self._idle.pop().close()
            except IndexError:
                break

    def request(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: CallTimeout = USE_CLIENT_DEFAULT,
    ) -> TransportResponse:
        """Sends one request over a persistent connection and reads the whole answer.

        `path` is absolute (the base URL's path included) and `headers` is the full header set from
        `headers_for`. Raises the httpx exception for the failure (see the module docstring).

        A connection that sat idle may have been closed by the server in the meantime. Such a call fails
        before the server's answer has started: the send fails with `BrokenPipeError` or
        `ConnectionResetError`, or the read of the status line finds the connection closed
        (`RemoteDisconnected`, also a `ConnectionResetError`). Only then is the call sent ONCE more on a
        fresh connection, for every method alike, because no byte of the answer was read and a closed
        connection is the one failure keep-alive makes routine. Never retried: a connection opened for
        this very call, a failure after the status line and the headers were read (the body, a timeout)
        and a failure on the fresh connection. The retry sends the request again, so a server that
        received a statement on a reused connection and dropped it without answering has the statement
        run twice; httpx would raise instead.
        """
        if self._closed:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        if isinstance(timeout, UseClientDefault):
            connect_timeout, io_timeout = self._connect_timeout, self._io_timeout
        else:
            connect_timeout, io_timeout = _split_timeout(timeout)
        try:
            slot = self._idle.pop()
        except IndexError:
            slot = self._new_slot()
        try:
            try:
                response = self._send(slot, method, path, headers, body, connect_timeout, io_timeout)
            except _STALE:
                if not slot.reused:
                    raise
                slot.close()
                self.stale_retries += 1
                slot = self._new_slot()
                response = self._send(slot, method, path, headers, body, connect_timeout, io_timeout)
            try:
                content = response.read()
            except TimeoutError as exc:
                raise httpx.ReadTimeout(str(exc) or "timed out") from exc
            encoding = response.msg.get("Content-Encoding")
            if encoding:
                content = _decode(content, encoding)
        except BaseException as exc:
            slot.close()
            mapped = _as_httpx_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        result = TransportResponse(response.status, content, response.msg)
        if self._closed or slot.conn.sock is None or len(self._idle) >= MAX_IDLE_CONNECTIONS:
            slot.close()
        else:
            slot.reused = True
            self._idle.append(slot)
        return result

    def _new_slot(self) -> _Slot:
        if self._https:
            return _Slot(http.client.HTTPSConnection(self._host, self._port, context=self._context))
        return _Slot(http.client.HTTPConnection(self._host, self._port))

    def _send(
        self,
        slot: _Slot,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes | None,
        connect_timeout: float | None,
        io_timeout: float | None,
    ) -> http.client.HTTPResponse:
        """Connects if needed, sends the request and reads the status line and headers.

        A stale-connection error propagates unchanged for `request` to retry; every other failure is
        raised here as the httpx exception for the phase it happened in.
        """
        conn = slot.conn
        if conn.sock is None:
            conn.timeout = connect_timeout
            try:
                conn.connect()
            except TimeoutError as exc:
                raise httpx.ConnectTimeout(str(exc) or "timed out") from exc
            except OSError as exc:
                raise httpx.ConnectError(str(exc)) from exc
            slot.io_timeout = _NOT_SET
        if slot.io_timeout != io_timeout:
            sock = conn.sock
            assert sock is not None
            sock.settimeout(io_timeout)
            slot.io_timeout = io_timeout
        try:
            conn.request(method, path, body=body, headers=headers)
        except _STALE:
            raise
        except TimeoutError as exc:
            raise httpx.WriteTimeout(str(exc) or "timed out") from exc
        except OSError as exc:
            raise httpx.WriteError(str(exc)) from exc
        try:
            return conn.getresponse()
        except _STALE:
            raise
        except TimeoutError as exc:
            raise httpx.ReadTimeout(str(exc) or "timed out") from exc


def _as_httpx_error(exc: BaseException) -> httpx.HTTPError | None:
    """The httpx exception for a socket-layer or protocol failure; `None` to let `exc` propagate as it is."""
    if isinstance(exc, httpx.HTTPError):
        return None
    if isinstance(exc, http.client.RemoteDisconnected):
        return httpx.RemoteProtocolError("Server disconnected without sending a response.")
    if isinstance(exc, http.client.HTTPException):
        return httpx.RemoteProtocolError(str(exc) or type(exc).__name__)
    if isinstance(exc, BrokenPipeError):
        return httpx.WriteError(str(exc))
    if isinstance(exc, TimeoutError):
        return httpx.ReadTimeout(str(exc) or "timed out")
    if isinstance(exc, OSError):
        return httpx.ReadError(str(exc))
    return None
