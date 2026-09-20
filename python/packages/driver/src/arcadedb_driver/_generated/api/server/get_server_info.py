from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.get_server_info_mode import GetServerInfoMode
from ...models.server_info import ServerInfo
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    mode: GetServerInfoMode | Unset = GetServerInfoMode.DEFAULT,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    json_mode: str | Unset = UNSET
    if not isinstance(mode, Unset):
        json_mode = mode.value

    params["mode"] = json_mode

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/server",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | ServerInfo | None:
    if response.status_code == 200:
        response_200 = ServerInfo.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | ServerInfo]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    mode: GetServerInfoMode | Unset = GetServerInfoMode.DEFAULT,
) -> Response[ErrorResponse | ServerInfo]:
    """Get server information

     Retrieves this server's identity and, depending on 'mode', its metrics and settings or its cluster
    state. The identity members - user, version, serverName, languages - are on every answer.

    Args:
        mode (GetServerInfoMode | Unset):  Default: GetServerInfoMode.DEFAULT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ServerInfo]
    """

    kwargs = _get_kwargs(
        mode=mode,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    mode: GetServerInfoMode | Unset = GetServerInfoMode.DEFAULT,
) -> ErrorResponse | ServerInfo | None:
    """Get server information

     Retrieves this server's identity and, depending on 'mode', its metrics and settings or its cluster
    state. The identity members - user, version, serverName, languages - are on every answer.

    Args:
        mode (GetServerInfoMode | Unset):  Default: GetServerInfoMode.DEFAULT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ServerInfo
    """

    return sync_detailed(
        client=client,
        mode=mode,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    mode: GetServerInfoMode | Unset = GetServerInfoMode.DEFAULT,
) -> Response[ErrorResponse | ServerInfo]:
    """Get server information

     Retrieves this server's identity and, depending on 'mode', its metrics and settings or its cluster
    state. The identity members - user, version, serverName, languages - are on every answer.

    Args:
        mode (GetServerInfoMode | Unset):  Default: GetServerInfoMode.DEFAULT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ServerInfo]
    """

    kwargs = _get_kwargs(
        mode=mode,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    mode: GetServerInfoMode | Unset = GetServerInfoMode.DEFAULT,
) -> ErrorResponse | ServerInfo | None:
    """Get server information

     Retrieves this server's identity and, depending on 'mode', its metrics and settings or its cluster
    state. The identity members - user, version, serverName, languages - are on every answer.

    Args:
        mode (GetServerInfoMode | Unset):  Default: GetServerInfoMode.DEFAULT.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ServerInfo
    """

    return (
        await asyncio_detailed(
            client=client,
            mode=mode,
        )
    ).parsed
