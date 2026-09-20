from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.security_admin_result import SecurityAdminResult
from ...models.update_user_request import UpdateUserRequest
from ...types import UNSET, Response


def _get_kwargs(
    *,
    body: UpdateUserRequest,
    name: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    params: dict[str, Any] = {}

    params["name"] = name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/v1/server/users",
        "params": params,
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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

    if response.status_code == 504:
        response_504 = ErrorResponse.from_dict(response.json())

        return response_504

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
    body: UpdateUserRequest,
    name: str,
) -> Response[ErrorResponse | SecurityAdminResult]:
    """Update user

     Updates an existing user's password and/or database assignments (root only). On an HA cluster the
    change is replicated to every node as a Raft entry.

    Args:
        name (str):
        body (UpdateUserRequest): Changes to apply to an existing user, named by the 'name' QUERY
            parameter rather than by the body. Both members are optional and an omitted one is left
            alone; a body carrying neither is accepted and changes nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SecurityAdminResult]
    """

    kwargs = _get_kwargs(
        body=body,
        name=name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: UpdateUserRequest,
    name: str,
) -> ErrorResponse | SecurityAdminResult | None:
    """Update user

     Updates an existing user's password and/or database assignments (root only). On an HA cluster the
    change is replicated to every node as a Raft entry.

    Args:
        name (str):
        body (UpdateUserRequest): Changes to apply to an existing user, named by the 'name' QUERY
            parameter rather than by the body. Both members are optional and an omitted one is left
            alone; a body carrying neither is accepted and changes nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SecurityAdminResult
    """

    return sync_detailed(
        client=client,
        body=body,
        name=name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: UpdateUserRequest,
    name: str,
) -> Response[ErrorResponse | SecurityAdminResult]:
    """Update user

     Updates an existing user's password and/or database assignments (root only). On an HA cluster the
    change is replicated to every node as a Raft entry.

    Args:
        name (str):
        body (UpdateUserRequest): Changes to apply to an existing user, named by the 'name' QUERY
            parameter rather than by the body. Both members are optional and an omitted one is left
            alone; a body carrying neither is accepted and changes nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SecurityAdminResult]
    """

    kwargs = _get_kwargs(
        body=body,
        name=name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: UpdateUserRequest,
    name: str,
) -> ErrorResponse | SecurityAdminResult | None:
    """Update user

     Updates an existing user's password and/or database assignments (root only). On an HA cluster the
    change is replicated to every node as a Raft entry.

    Args:
        name (str):
        body (UpdateUserRequest): Changes to apply to an existing user, named by the 'name' QUERY
            parameter rather than by the body. Both members are optional and an omitted one is left
            alone; a body carrying neither is accepted and changes nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SecurityAdminResult
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            name=name,
        )
    ).parsed
