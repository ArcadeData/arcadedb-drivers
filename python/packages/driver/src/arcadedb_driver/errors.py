"""The facade's error type.

`ArcadeDBServer.raw` - the generated client - never raises this, or anything
else: it returns a `Response` whose `status_code` the caller inspects. That
asymmetry is deliberate and mirrors `@arcadedb/driver`, where `raw` returns
`{ data, error }` while every facade method throws.
"""

from __future__ import annotations

import json
from typing import Any

from ._generated.models.error_response import ErrorResponse
from ._generated.types import Response

#: The server sets this on every response, generating a value when the client sent
#: none, so it is a usable correlation id unconditionally - not only when the caller
#: supplied its own.
REQUEST_ID_HEADER = "X-Request-Id"


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


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
    """

    def __init__(self, status: int, body: object = None, request_id: str | None = None) -> None:
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
        super().__init__(self.error or self.detail or f"ArcadeDB request failed with status {self.status}")

    @classmethod
    def from_response(cls, response: Response[Any]) -> ArcadeDBError:
        """Builds an error from a generated `Response`.

        Prefers the already-parsed `ErrorResponse` when the contract documented one
        for this status, and falls back to re-reading the raw bytes when it did not.
        """
        body: object = response.parsed if isinstance(response.parsed, ErrorResponse) else response.content
        return cls(int(response.status_code), body, response.headers.get(REQUEST_ID_HEADER))


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
