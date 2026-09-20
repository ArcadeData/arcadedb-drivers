from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.security_admin_result import SecurityAdminResult
from ...types import UNSET, Response


def _get_kwargs(
    *,
    database: str,
    name: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["database"] = database

    params["name"] = name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/server/groups",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | SecurityAdminResult | None:
    if response.status_code == 200:
        response_200 = SecurityAdminResult.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = ErrorResponse.from_dict(response.json())

        return response_403

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | SecurityAdminResult]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    database: str,
    name: str,
) -> Response[ErrorResponse | SecurityAdminResult]:
    """Delete group

     Deletes a security group (root only)

    Args:
        database (str):
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SecurityAdminResult]
    """

    kwargs = _get_kwargs(
        database=database,
        name=name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    database: str,
    name: str,
) -> ErrorResponse | SecurityAdminResult | None:
    """Delete group

     Deletes a security group (root only)

    Args:
        database (str):
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SecurityAdminResult
    """

    return sync_detailed(
        client=client,
        database=database,
        name=name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    database: str,
    name: str,
) -> Response[ErrorResponse | SecurityAdminResult]:
    """Delete group

     Deletes a security group (root only)

    Args:
        database (str):
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SecurityAdminResult]
    """

    kwargs = _get_kwargs(
        database=database,
        name=name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    database: str,
    name: str,
) -> ErrorResponse | SecurityAdminResult | None:
    """Delete group

     Deletes a security group (root only)

    Args:
        database (str):
        name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SecurityAdminResult
    """

    return (
        await asyncio_detailed(
            client=client,
            database=database,
            name=name,
        )
    ).parsed
