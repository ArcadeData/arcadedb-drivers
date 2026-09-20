"""The data plane: `query`, `command`, and the transaction primitives.

Everything here takes the generated `Client` explicitly rather than reaching for a
module-level one, so the sync and async facades can share the request-building and
envelope-normalising code without either importing the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeVar

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
    itself never claimed. 26.10.1-SNAPSHOT made `limit`, `returned` and `truncated`
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

    26.10.1-SNAPSHOT widened `result` into a union: an array of rows under the default
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
