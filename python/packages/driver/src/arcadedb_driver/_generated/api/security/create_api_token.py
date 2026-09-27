from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.create_api_token_request import CreateApiTokenRequest
from ...models.create_api_token_response import CreateApiTokenResponse
from ...models.error_response import ErrorResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: CreateApiTokenRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server/api-tokens",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> CreateApiTokenResponse | ErrorResponse | None:
    if response.status_code == 201:
        response_201 = CreateApiTokenResponse.from_dict(response.json())

        return response_201

    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = ErrorResponse.from_dict(response.json())

        return response_403

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 412:
        response_412 = ErrorResponse.from_dict(response.json())

        return response_412

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
) -> Response[CreateApiTokenResponse | ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CreateApiTokenRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[CreateApiTokenResponse | ErrorResponse]:
    """Create API token

     Creates a new API token (root only). The plaintext token is returned only once in the response. On
    an HA cluster a follower checks the transport of the client connection, then forwards the request to
    the leader.

    Args:
        x_request_id (str | Unset):
        body (CreateApiTokenRequest): A token to issue

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateApiTokenResponse | ErrorResponse]
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
    body: CreateApiTokenRequest,
    x_request_id: str | Unset = UNSET,
) -> CreateApiTokenResponse | ErrorResponse | None:
    """Create API token

     Creates a new API token (root only). The plaintext token is returned only once in the response. On
    an HA cluster a follower checks the transport of the client connection, then forwards the request to
    the leader.

    Args:
        x_request_id (str | Unset):
        body (CreateApiTokenRequest): A token to issue

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateApiTokenResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: CreateApiTokenRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[CreateApiTokenResponse | ErrorResponse]:
    """Create API token

     Creates a new API token (root only). The plaintext token is returned only once in the response. On
    an HA cluster a follower checks the transport of the client connection, then forwards the request to
    the leader.

    Args:
        x_request_id (str | Unset):
        body (CreateApiTokenRequest): A token to issue

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateApiTokenResponse | ErrorResponse]
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
    body: CreateApiTokenRequest,
    x_request_id: str | Unset = UNSET,
) -> CreateApiTokenResponse | ErrorResponse | None:
    """Create API token

     Creates a new API token (root only). The plaintext token is returned only once in the response. On
    an HA cluster a follower checks the transport of the client connection, then forwards the request to
    the leader.

    Args:
        x_request_id (str | Unset):
        body (CreateApiTokenRequest): A token to issue

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateApiTokenResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
