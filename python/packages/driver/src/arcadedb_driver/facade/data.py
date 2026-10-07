"""The data plane: `query`, `command`, and the transaction primitives.

Everything here takes the generated `Client` explicitly rather than reaching for a
module-level one, so the sync and async facades can share the request-building and
envelope-normalising code without either importing the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from urllib.parse import quote

import httpx

from .._generated.models.command_request import CommandRequest
from .._generated.models.command_request_params import CommandRequestParams
from .._generated.models.query_request import QueryRequest
from .._generated.models.query_request_params import QueryRequestParams
from .._generated.models.query_response import QueryResponse
from .._generated.types import UNSET, Unset
from ..errors import ArcadeDBError

#: Request header carrying the session id that scopes a call to one transaction.
SESSION_HEADER = "arcadedb-session-id"

#: Query/command language, as accepted by the `/query` and `/command` endpoints.
QueryLanguage = Literal["sql", "cypher", "gremlin", "graphql", "mongo"]

T = TypeVar("T")


def _or(value: T | Unset, fallback: T) -> T:
    return fallback if isinstance(value, Unset) else value


@dataclass(frozen=True, slots=True)
class QueryEnvelope:
    """The whole result envelope `query`/`command` return - not just the rows.

    `truncated` means the serializer's row cap stopped mid-serialization with rows
    still pending, so `result` is incomplete: a caller that reads `result` and
    ignores `truncated` can silently work off a partial answer.

    `QueryResponse` used to declare no `required` list, so every field was optional on
    the wire and this client defaulted each one it did not get - `limit` to `-1`,
    `returned` to `0`, `truncated` to `False` - asserting a completeness the server
    itself never claimed. 26.10.1 made `limit`, `returned` and `truncated`
    required, and the generated model now types them as plain `int`/`bool` that
    `from_dict` pops without a fallback. `truncated is False` is therefore a server
    statement now, not a client-side guess.

    The `_or(...)` fallbacks in `to_envelope` below are consequently unreachable for
    those three fields. They are kept rather than deleted because `result` still needs
    one and because the fallbacks cost nothing if a later contract loosens the list
    again; nobody should go looking for the code path that triggers them today.
    """

    result: list[dict[str, Any]]
    limit: int
    returned: int
    truncated: bool


def to_envelope(data: QueryResponse) -> QueryEnvelope:
    """Normalises a generated `QueryResponse` into the public envelope.

    Also flattens each row out of `QueryResponseResultType0Item`'s additional-properties
    wrapper into the plain dict a caller expects.

    26.10.1 widened `result` into a union: an array of rows under the default
    `record` serializer, and a single `{vertices, edges}` object - plus `records` under
    `studio` - under the two graph serializers. `QueryEnvelope.result` is a list of rows
    and cannot represent the second shape.

    `build_query_request` never sends `serializer`, so the server always picks `record`
    and the graph arm cannot arrive here. The check below is nonetheless a raise rather
    than a cast: "unreachable" is a property of today's request builder, not of the
    contract, and the day `serializer` becomes a parameter this has to fail with a
    sentence explaining why rather than with `TypeError: 'QueryResponseResultType1'
    object is not iterable` from inside a comprehension.

    `ArcadeDBError(200, ...)`, not a builtin: "the server answered 200 in a shape this
    client cannot represent" is already an `ArcadeDBError` everywhere else here - see
    `stream.py`'s in-band error event - and the README's "Two error models" section
    tells callers that `except ArcadeDBError` around `query`/`command` is enough. A
    bare `TypeError` would slip straight through that. The TypeScript sibling throws
    `ArcadeDBError` for this same guard.
    """
    rows = _or(data.result, [])
    if not isinstance(rows, list):
        raise ArcadeDBError(
            200,
            {
                "error": "the server answered with a graph-serializer result object, but this call expected rows",
                "detail": (
                    "QueryResponse.result is {vertices, edges}, which QueryEnvelope cannot represent. "
                    "This client never asks for a graph serializer - it sends no 'serializer' field."
                ),
            },
        )
    return QueryEnvelope(
        result=[row.to_dict() for row in rows],
        limit=_or(data.limit, -1),
        returned=_or(data.returned, 0),
        truncated=_or(data.truncated, False),
    )


def build_query_request(
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None,
    limit: int | None,
) -> QueryRequest:
    """Builds the body for `POST /api/v1/query/{database}`.

    `params` is converted with `from_dict` because the generated params type is an
    "untyped object" artifact rather than a real restriction. `command` and
    `language` are passed through with their real types, so a contract change to
    either still fails the typecheck here rather than only on the wire.
    """
    return QueryRequest(
        command=command,
        language=language,
        params=UNSET if params is None else QueryRequestParams.from_dict(params),
        limit=UNSET if limit is None else limit,
    )


def build_command_request(
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None,
) -> CommandRequest:
    """Builds the body for `POST /api/v1/command/{database}`.

    `language` is a required field here, unlike on `/query`, matching the server's
    `PostCommandHandler`, which rejects a request without it.

    NOTE: `CommandRequest` also carries an optional `limit` in the current contract.
    It is deliberately NOT exposed on `command()`. `@arcadedb/driver` does not
    expose it either, and keeping the two clients' public surfaces identical matters
    more than one optional field. Adding it is additive and belongs in a change that
    does it for both clients at once.
    """
    return CommandRequest(
        command=command,
        language=language,
        params=UNSET if params is None else CommandRequestParams.from_dict(params),
    )


def session_kwarg(session_id: str | None) -> str | Unset:
    """The `arcadedb_session_id` argument value: the id inside a transaction, `UNSET` outside one.

    The contract declares the header, so the generator emits it as a keyword
    argument on every data-plane and transaction operation - no header plumbing
    needed.
    """
    return UNSET if session_id is None else session_id


def query_body(
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None,
    limit: int | None,
) -> dict[str, Any]:
    """The JSON body of `POST /api/v1/query/{database}`, as the plain dict `build_query_request(...).to_dict()` yields.

    Same keys in the same order, so the bytes on the wire do not change. This is what
    `query` sends: building the generated request model only to turn it straight back
    into this dict was pure overhead on the hot path. `build_query_request` stays for
    the streaming calls.
    """
    body: dict[str, Any] = {"command": command, "language": language}
    if limit is not None:
        body["limit"] = limit
    if params is not None:
        body["params"] = dict(params)
    return body


def command_body(
    *,
    language: QueryLanguage,
    command: str,
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    """The JSON body of `POST /api/v1/command/{database}`; the `command` twin of `query_body`."""
    body: dict[str, Any] = {"command": command, "language": language}
    if params is not None:
        body["params"] = dict(params)
    return body


def request_headers(session_id: str | None) -> dict[str, str]:
    """The per-request headers of a `/query` or `/command` call, in the order the generated operation builds them.

    The session id (inside a transaction only) comes first, then `Content-Type`. httpx would add the content type
    itself for `json=`, but after `Content-Length`; stating it here keeps the request byte for byte what it was.
    """
    if session_id is None:
        return {"Content-Type": "application/json"}
    return {SESSION_HEADER: session_id, "Content-Type": "application/json"}


class DataUrls:
    """The absolute `/query/{database}` and `/command/{database}` URLs of one database on one httpx client.

    The generated operations pass httpx a RELATIVE path, which httpx re-parses and
    merges with its `base_url` on every call. Resolving it once here, through
    `build_request` so the result is exactly what httpx would have built, removes
    about a fifth of a one-row read's cost. The URLs are rebuilt when the client's
    `base_url` object changes (`set_httpx_client`) or when the database name does
    (`ArcadeDBDatabase.name` is a public attribute), so neither goes stale.
    Sync and async clients share this class: `build_request` is synchronous on both.
    """

    __slots__ = ("_base", "_command", "_name", "_query")

    def __init__(self) -> None:
        self._base: httpx.URL | None = None
        self._name: str | None = None
        self._query: httpx.URL
        self._command: httpx.URL

    def _resolve(self, http: httpx.Client | httpx.AsyncClient, database: str) -> None:
        quoted = quote(str(database), safe="")
        self._query = http.build_request("POST", f"/api/v1/query/{quoted}").url
        self._command = http.build_request("POST", f"/api/v1/command/{quoted}").url
        self._base = http.base_url
        self._name = database

    def query(self, http: httpx.Client | httpx.AsyncClient, database: str) -> httpx.URL:
        if self._base is not http.base_url or self._name != database:
            self._resolve(http, database)
        return self._query

    def command(self, http: httpx.Client | httpx.AsyncClient, database: str) -> httpx.URL:
        if self._base is not http.base_url or self._name != database:
            self._resolve(http, database)
        return self._command


def fast_envelope(response: httpx.Response) -> QueryEnvelope | None:
    """The envelope of a plain `200` row result, read straight from the decoded JSON - or `None`.

    `None` means "this response is not the common case": the caller then runs the
    generated parse (`_build_response`, `unwrap`, `to_envelope`) on the SAME httpx
    response, so every error, every odd shape and every `explain` response behaves as
    it always did. The fast path only answers when the generated path would have
    produced the same envelope without raising: a `200`, a JSON object holding
    `limit`, `returned`, `truncated` and a `result` list of objects, and neither
    `explain` nor `explainPlan`. It skips one `QueryResponse` and one attrs model per
    row, each copied twice.
    """
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    if type(data) is not dict:
        return None
    rows = data.get("result")
    if type(rows) is not list or "explain" in data or "explainPlan" in data:
        return None
    try:
        limit = data["limit"]
        returned = data["returned"]
        truncated = data["truncated"]
    except KeyError:
        return None
    for row in rows:
        if type(row) is not dict:
            return None
    return QueryEnvelope(result=rows, limit=limit, returned=returned, truncated=truncated)
