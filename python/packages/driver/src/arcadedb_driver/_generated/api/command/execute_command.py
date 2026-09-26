from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.command_request import CommandRequest
from ...models.error_response import ErrorResponse
from ...models.execute_command_accept import ExecuteCommandAccept
from ...models.query_response import QueryResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    body: CommandRequest,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteCommandAccept | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(arcadedb_session_id, Unset):
        headers["arcadedb-session-id"] = arcadedb_session_id

    if not isinstance(accept, Unset):
        headers["Accept"] = str(accept)

    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/command/{database}".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | QueryResponse | None:
    if response.status_code == 200:
        response_200 = QueryResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = ErrorResponse.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = ErrorResponse.from_dict(response.json())

        return response_413

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | QueryResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteCommandAccept | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | QueryResponse]:
    r"""Execute command

     Executes a database command. INSERT INTO a TIMESERIES type is NOT atomic with the transaction that
    contains it: the samples are committed as they are appended and a rollback does not take them back.
    Every other INSERT target behaves normally. When 'Accept' requests the ndjson encoding, only a
    statement provably read-only may stream: one that writes - INSERT, UPDATE, DELETE, DDL, BACKUP
    DATABASE, or one this analysis cannot classify - is refused with 400 before it runs, because a
    streamed response puts its status code on the wire ahead of the rows and so cannot report a
    statement that fails half-way through. Request the buffered 'application/json' encoding for it
    instead.

    EXPLAIN is refused on the stream for a different reason and with its own 400 (\"EXPLAIN produces a
    plan, not a row stream\"): it is read-only and passes the gate above, but its answer is a plan
    rather than rows, and a stream of rows plus a stats trailer has nowhere to carry one. Request it
    buffered, where the plan arrives in the 'explain' and 'explainPlan' properties of the envelope and
    'result' is empty. All three operations answer EXPLAIN this way; until issue #7575 the GET operation
    reached neither rule and answered the plan as a result row instead.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteCommandAccept | Unset):
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
        accept=accept,
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteCommandAccept | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | QueryResponse | None:
    r"""Execute command

     Executes a database command. INSERT INTO a TIMESERIES type is NOT atomic with the transaction that
    contains it: the samples are committed as they are appended and a rollback does not take them back.
    Every other INSERT target behaves normally. When 'Accept' requests the ndjson encoding, only a
    statement provably read-only may stream: one that writes - INSERT, UPDATE, DELETE, DDL, BACKUP
    DATABASE, or one this analysis cannot classify - is refused with 400 before it runs, because a
    streamed response puts its status code on the wire ahead of the rows and so cannot report a
    statement that fails half-way through. Request the buffered 'application/json' encoding for it
    instead.

    EXPLAIN is refused on the stream for a different reason and with its own 400 (\"EXPLAIN produces a
    plan, not a row stream\"): it is read-only and passes the gate above, but its answer is a plan
    rather than rows, and a stream of rows plus a stats trailer has nowhere to carry one. Request it
    buffered, where the plan arrives in the 'explain' and 'explainPlan' properties of the envelope and
    'result' is empty. All three operations answer EXPLAIN this way; until issue #7575 the GET operation
    reached neither rule and answered the plan as a result row instead.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteCommandAccept | Unset):
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | QueryResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
        accept=accept,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteCommandAccept | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | QueryResponse]:
    r"""Execute command

     Executes a database command. INSERT INTO a TIMESERIES type is NOT atomic with the transaction that
    contains it: the samples are committed as they are appended and a rollback does not take them back.
    Every other INSERT target behaves normally. When 'Accept' requests the ndjson encoding, only a
    statement provably read-only may stream: one that writes - INSERT, UPDATE, DELETE, DDL, BACKUP
    DATABASE, or one this analysis cannot classify - is refused with 400 before it runs, because a
    streamed response puts its status code on the wire ahead of the rows and so cannot report a
    statement that fails half-way through. Request the buffered 'application/json' encoding for it
    instead.

    EXPLAIN is refused on the stream for a different reason and with its own 400 (\"EXPLAIN produces a
    plan, not a row stream\"): it is read-only and passes the gate above, but its answer is a plan
    rather than rows, and a stream of rows plus a stats trailer has nowhere to carry one. Request it
    buffered, where the plan arrives in the 'explain' and 'explainPlan' properties of the envelope and
    'result' is empty. All three operations answer EXPLAIN this way; until issue #7575 the GET operation
    reached neither rule and answered the plan as a result row instead.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteCommandAccept | Unset):
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
        accept=accept,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteCommandAccept | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | QueryResponse | None:
    r"""Execute command

     Executes a database command. INSERT INTO a TIMESERIES type is NOT atomic with the transaction that
    contains it: the samples are committed as they are appended and a rollback does not take them back.
    Every other INSERT target behaves normally. When 'Accept' requests the ndjson encoding, only a
    statement provably read-only may stream: one that writes - INSERT, UPDATE, DELETE, DDL, BACKUP
    DATABASE, or one this analysis cannot classify - is refused with 400 before it runs, because a
    streamed response puts its status code on the wire ahead of the rows and so cannot report a
    statement that fails half-way through. Request the buffered 'application/json' encoding for it
    instead.

    EXPLAIN is refused on the stream for a different reason and with its own 400 (\"EXPLAIN produces a
    plan, not a row stream\"): it is read-only and passes the gate above, but its answer is a plan
    rather than rows, and a stream of rows plus a stats trailer has nowhere to carry one. Request it
    buffered, where the plan arrives in the 'explain' and 'explainPlan' properties of the envelope and
    'result' is empty. All three operations answer EXPLAIN this way; until issue #7575 the GET operation
    reached neither rule and answered the plan as a result row instead.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteCommandAccept | Unset):
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | QueryResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            body=body,
            arcadedb_session_id=arcadedb_session_id,
            accept=accept,
            x_request_id=x_request_id,
        )
    ).parsed
