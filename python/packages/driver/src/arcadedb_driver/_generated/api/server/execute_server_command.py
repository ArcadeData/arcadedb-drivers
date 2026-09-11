from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.command_request import CommandRequest
from ...models.error_response import ErrorResponse
from ...models.query_response import QueryResponse
from ...types import Response


def _get_kwargs(
    *,
    body: CommandRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

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
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
) -> Response[ErrorResponse | QueryResponse]:
    """Execute server command

     Executes administrative commands on the server (root user only). Available commands: create
    database, drop database, open database, close database, restore database <name> <url>, import
    database <name> <url>, create user, drop user, shutdown, set server setting, get server events,
    align database, connect cluster <address>, disconnect cluster. Both restore and import support SSE
    progress streaming via Accept: text/event-stream header. connect cluster is dispatched but not
    implemented by the current HA implementation and always fails; use the cluster configuration to join
    nodes

    Args:
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
) -> ErrorResponse | QueryResponse | None:
    """Execute server command

     Executes administrative commands on the server (root user only). Available commands: create
    database, drop database, open database, close database, restore database <name> <url>, import
    database <name> <url>, create user, drop user, shutdown, set server setting, get server events,
    align database, connect cluster <address>, disconnect cluster. Both restore and import support SSE
    progress streaming via Accept: text/event-stream header. connect cluster is dispatched but not
    implemented by the current HA implementation and always fails; use the cluster configuration to join
    nodes

    Args:
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
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
) -> Response[ErrorResponse | QueryResponse]:
    """Execute server command

     Executes administrative commands on the server (root user only). Available commands: create
    database, drop database, open database, close database, restore database <name> <url>, import
    database <name> <url>, create user, drop user, shutdown, set server setting, get server events,
    align database, connect cluster <address>, disconnect cluster. Both restore and import support SSE
    progress streaming via Accept: text/event-stream header. connect cluster is dispatched but not
    implemented by the current HA implementation and always fails; use the cluster configuration to join
    nodes

    Args:
        body (CommandRequest): Command request object

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: CommandRequest,
) -> ErrorResponse | QueryResponse | None:
    """Execute server command

     Executes administrative commands on the server (root user only). Available commands: create
    database, drop database, open database, close database, restore database <name> <url>, import
    database <name> <url>, create user, drop user, shutdown, set server setting, get server events,
    align database, connect cluster <address>, disconnect cluster. Both restore and import support SSE
    progress streaming via Accept: text/event-stream header. connect cluster is dispatched but not
    implemented by the current HA implementation and always fails; use the cluster configuration to join
    nodes

    Args:
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
        )
    ).parsed
