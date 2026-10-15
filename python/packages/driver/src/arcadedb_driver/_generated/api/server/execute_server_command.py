from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.command_request import CommandRequest
from ...models.error_response import ErrorResponse
from ...models.query_response import QueryResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: CommandRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server",
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

    if response.status_code == 503:
        response_503 = ErrorResponse.from_dict(response.json())

        return response_503

    if response.status_code == 504:
        response_504 = ErrorResponse.from_dict(response.json())

        return response_504

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
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | QueryResponse]:
    """Execute server command

     Executes administrative commands on the server (root user only, except 'list databases' and the
    commands on running work below). Available commands: create database, drop database, open database,
    close database, restore database <name> <url>, import database <name> <url>, create user, drop user,
    shutdown, set server setting, get server events, align database, connect cluster <address>,
    disconnect cluster. Both restore and import support SSE progress streaming via Accept: text/event-
    stream header. connect cluster <address> adds the server at <address> to this server's cluster - the
    operator alias of POST /api/v1/cluster/peer - where <address> is one entry of arcadedb.ha.serverList
    ([name@]host[:raftPort[:httpPort]] or the host:{raft:..,http:..} object form). It answers 400 for a
    blank or malformed address, 500 when this server is not running an HA implementation that supports
    runtime membership, and 503 when the server joined but one of the three security documents could not
    be seeded to it - the same answer POST /api/v1/cluster/peer gives that condition, with the failing
    documents in 'failedSeeds'. The join itself stands in that case; re-running the command is
    idempotent on the membership change and reissues the seed. Note the direction: it never makes THIS
    server join another cluster, and an address that resolves to this server is answered 400 rather than
    accepted as a no-op. To make a running server join a cluster it is not configured for, issue this
    same command on a server that is already a member of that cluster, or declare arcadedb.ha.serverList
    and restart. Running work (any authenticated user; root sees and stops every statement, another user
    only their own, and someone else's is answered 'not found'): 'list queries [database <name>] [tag
    <label>]' lists the statements this server is running, with the label a client gave them in the
    X-ArcadeDB-Query-Tag request header; 'terminate query <id>' and 'terminate queries tag <label>' stop
    them and wait for them to end, up to the payload's 'wait' in milliseconds (default 5000, at most
    10000), answering each with a status: 'terminated' (it stopped and what it wrote was rolled back),
    'completed' (it ended on its own before it noticed: what it did stands), 'terminating' (not stopped
    yet) or 'not found'; 'list transactions' lists the open transaction sessions and 'terminate
    transaction <session id>' rolls one back and ends it. A command terminated inside a session ends the
    session too, rolling it back, while a terminated read leaves the session to its client: the answer
    for a statement that ran in a session carries its 'sessionId' and 'sessionOpen' (for a 'terminating'
    statement only the state at the time of the answer: a command ends its session as it stops). A
    terminated request is answered 409 'Query terminated'. These commands are never forwarded to the
    leader: each server lists and stops its own work

    Args:
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        body=body,
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | QueryResponse | None:
    """Execute server command

     Executes administrative commands on the server (root user only, except 'list databases' and the
    commands on running work below). Available commands: create database, drop database, open database,
    close database, restore database <name> <url>, import database <name> <url>, create user, drop user,
    shutdown, set server setting, get server events, align database, connect cluster <address>,
    disconnect cluster. Both restore and import support SSE progress streaming via Accept: text/event-
    stream header. connect cluster <address> adds the server at <address> to this server's cluster - the
    operator alias of POST /api/v1/cluster/peer - where <address> is one entry of arcadedb.ha.serverList
    ([name@]host[:raftPort[:httpPort]] or the host:{raft:..,http:..} object form). It answers 400 for a
    blank or malformed address, 500 when this server is not running an HA implementation that supports
    runtime membership, and 503 when the server joined but one of the three security documents could not
    be seeded to it - the same answer POST /api/v1/cluster/peer gives that condition, with the failing
    documents in 'failedSeeds'. The join itself stands in that case; re-running the command is
    idempotent on the membership change and reissues the seed. Note the direction: it never makes THIS
    server join another cluster, and an address that resolves to this server is answered 400 rather than
    accepted as a no-op. To make a running server join a cluster it is not configured for, issue this
    same command on a server that is already a member of that cluster, or declare arcadedb.ha.serverList
    and restart. Running work (any authenticated user; root sees and stops every statement, another user
    only their own, and someone else's is answered 'not found'): 'list queries [database <name>] [tag
    <label>]' lists the statements this server is running, with the label a client gave them in the
    X-ArcadeDB-Query-Tag request header; 'terminate query <id>' and 'terminate queries tag <label>' stop
    them and wait for them to end, up to the payload's 'wait' in milliseconds (default 5000, at most
    10000), answering each with a status: 'terminated' (it stopped and what it wrote was rolled back),
    'completed' (it ended on its own before it noticed: what it did stands), 'terminating' (not stopped
    yet) or 'not found'; 'list transactions' lists the open transaction sessions and 'terminate
    transaction <session id>' rolls one back and ends it. A command terminated inside a session ends the
    session too, rolling it back, while a terminated read leaves the session to its client: the answer
    for a statement that ran in a session carries its 'sessionId' and 'sessionOpen' (for a 'terminating'
    statement only the state at the time of the answer: a command ends its session as it stops). A
    terminated request is answered 409 'Query terminated'. These commands are never forwarded to the
    leader: each server lists and stops its own work

    Args:
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | QueryResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | QueryResponse]:
    """Execute server command

     Executes administrative commands on the server (root user only, except 'list databases' and the
    commands on running work below). Available commands: create database, drop database, open database,
    close database, restore database <name> <url>, import database <name> <url>, create user, drop user,
    shutdown, set server setting, get server events, align database, connect cluster <address>,
    disconnect cluster. Both restore and import support SSE progress streaming via Accept: text/event-
    stream header. connect cluster <address> adds the server at <address> to this server's cluster - the
    operator alias of POST /api/v1/cluster/peer - where <address> is one entry of arcadedb.ha.serverList
    ([name@]host[:raftPort[:httpPort]] or the host:{raft:..,http:..} object form). It answers 400 for a
    blank or malformed address, 500 when this server is not running an HA implementation that supports
    runtime membership, and 503 when the server joined but one of the three security documents could not
    be seeded to it - the same answer POST /api/v1/cluster/peer gives that condition, with the failing
    documents in 'failedSeeds'. The join itself stands in that case; re-running the command is
    idempotent on the membership change and reissues the seed. Note the direction: it never makes THIS
    server join another cluster, and an address that resolves to this server is answered 400 rather than
    accepted as a no-op. To make a running server join a cluster it is not configured for, issue this
    same command on a server that is already a member of that cluster, or declare arcadedb.ha.serverList
    and restart. Running work (any authenticated user; root sees and stops every statement, another user
    only their own, and someone else's is answered 'not found'): 'list queries [database <name>] [tag
    <label>]' lists the statements this server is running, with the label a client gave them in the
    X-ArcadeDB-Query-Tag request header; 'terminate query <id>' and 'terminate queries tag <label>' stop
    them and wait for them to end, up to the payload's 'wait' in milliseconds (default 5000, at most
    10000), answering each with a status: 'terminated' (it stopped and what it wrote was rolled back),
    'completed' (it ended on its own before it noticed: what it did stands), 'terminating' (not stopped
    yet) or 'not found'; 'list transactions' lists the open transaction sessions and 'terminate
    transaction <session id>' rolls one back and ends it. A command terminated inside a session ends the
    session too, rolling it back, while a terminated read leaves the session to its client: the answer
    for a statement that ran in a session carries its 'sessionId' and 'sessionOpen' (for a 'terminating'
    statement only the state at the time of the answer: a command ends its session as it stops). A
    terminated request is answered 409 'Query terminated'. These commands are never forwarded to the
    leader: each server lists and stops its own work

    Args:
        x_request_id (str | Unset):
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        body=body,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | QueryResponse | None:
    """Execute server command

     Executes administrative commands on the server (root user only, except 'list databases' and the
    commands on running work below). Available commands: create database, drop database, open database,
    close database, restore database <name> <url>, import database <name> <url>, create user, drop user,
    shutdown, set server setting, get server events, align database, connect cluster <address>,
    disconnect cluster. Both restore and import support SSE progress streaming via Accept: text/event-
    stream header. connect cluster <address> adds the server at <address> to this server's cluster - the
    operator alias of POST /api/v1/cluster/peer - where <address> is one entry of arcadedb.ha.serverList
    ([name@]host[:raftPort[:httpPort]] or the host:{raft:..,http:..} object form). It answers 400 for a
    blank or malformed address, 500 when this server is not running an HA implementation that supports
    runtime membership, and 503 when the server joined but one of the three security documents could not
    be seeded to it - the same answer POST /api/v1/cluster/peer gives that condition, with the failing
    documents in 'failedSeeds'. The join itself stands in that case; re-running the command is
    idempotent on the membership change and reissues the seed. Note the direction: it never makes THIS
    server join another cluster, and an address that resolves to this server is answered 400 rather than
    accepted as a no-op. To make a running server join a cluster it is not configured for, issue this
    same command on a server that is already a member of that cluster, or declare arcadedb.ha.serverList
    and restart. Running work (any authenticated user; root sees and stops every statement, another user
    only their own, and someone else's is answered 'not found'): 'list queries [database <name>] [tag
    <label>]' lists the statements this server is running, with the label a client gave them in the
    X-ArcadeDB-Query-Tag request header; 'terminate query <id>' and 'terminate queries tag <label>' stop
    them and wait for them to end, up to the payload's 'wait' in milliseconds (default 5000, at most
    10000), answering each with a status: 'terminated' (it stopped and what it wrote was rolled back),
    'completed' (it ended on its own before it noticed: what it did stands), 'terminating' (not stopped
    yet) or 'not found'; 'list transactions' lists the open transaction sessions and 'terminate
    transaction <session id>' rolls one back and ends it. A command terminated inside a session ends the
    session too, rolling it back, while a terminated read leaves the session to its client: the answer
    for a statement that ran in a session carries its 'sessionId' and 'sessionOpen' (for a 'terminating'
    statement only the state at the time of the answer: a command ends its session as it stops). A
    terminated request is answered 409 'Query terminated'. These commands are never forwarded to the
    leader: each server lists and stops its own work

    Args:
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
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
