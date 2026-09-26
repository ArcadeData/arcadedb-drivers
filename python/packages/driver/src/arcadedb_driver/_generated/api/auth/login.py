from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.login_response import LoginResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/login",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | LoginResponse | None:
    if response.status_code == 200:
        response_200 = LoginResponse.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = ErrorResponse.from_dict(response.json())

        return response_403

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if response.status_code == 503:
        response_503 = ErrorResponse.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | LoginResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | LoginResponse]:
    """Create an authentication session

     Exchanges the credentials on the Authorization header for a session token prefixed 'AU-'. The token
    is then presented as a bearer token on subsequent requests. This operation takes no request body:
    the credentials travel on the header, and geolocation metadata is read from the CF-IPCountry, CF-
    IPCity, CF-Connecting-IP, X-Forwarded-For, and User-Agent headers when a proxy supplies them (each
    is stored truncated to 256 characters). Answers 503 when the server already holds
    'arcadedb.server.httpAuthSessionMax' concurrent sessions and none could be reclaimed; a principal
    that reaches 'arcadedb.server.httpAuthSessionMaxPerUser' instead has its own oldest session evicted
    and still receives a token.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | LoginResponse]
    """

    kwargs = _get_kwargs(
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | LoginResponse | None:
    """Create an authentication session

     Exchanges the credentials on the Authorization header for a session token prefixed 'AU-'. The token
    is then presented as a bearer token on subsequent requests. This operation takes no request body:
    the credentials travel on the header, and geolocation metadata is read from the CF-IPCountry, CF-
    IPCity, CF-Connecting-IP, X-Forwarded-For, and User-Agent headers when a proxy supplies them (each
    is stored truncated to 256 characters). Answers 503 when the server already holds
    'arcadedb.server.httpAuthSessionMax' concurrent sessions and none could be reclaimed; a principal
    that reaches 'arcadedb.server.httpAuthSessionMaxPerUser' instead has its own oldest session evicted
    and still receives a token.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | LoginResponse
    """

    return sync_detailed(
        client=client,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | LoginResponse]:
    """Create an authentication session

     Exchanges the credentials on the Authorization header for a session token prefixed 'AU-'. The token
    is then presented as a bearer token on subsequent requests. This operation takes no request body:
    the credentials travel on the header, and geolocation metadata is read from the CF-IPCountry, CF-
    IPCity, CF-Connecting-IP, X-Forwarded-For, and User-Agent headers when a proxy supplies them (each
    is stored truncated to 256 characters). Answers 503 when the server already holds
    'arcadedb.server.httpAuthSessionMax' concurrent sessions and none could be reclaimed; a principal
    that reaches 'arcadedb.server.httpAuthSessionMaxPerUser' instead has its own oldest session evicted
    and still receives a token.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | LoginResponse]
    """

    kwargs = _get_kwargs(
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | LoginResponse | None:
    """Create an authentication session

     Exchanges the credentials on the Authorization header for a session token prefixed 'AU-'. The token
    is then presented as a bearer token on subsequent requests. This operation takes no request body:
    the credentials travel on the header, and geolocation metadata is read from the CF-IPCountry, CF-
    IPCity, CF-Connecting-IP, X-Forwarded-For, and User-Agent headers when a proxy supplies them (each
    is stored truncated to 256 characters). Answers 503 when the server already holds
    'arcadedb.server.httpAuthSessionMax' concurrent sessions and none could be reclaimed; a principal
    that reaches 'arcadedb.server.httpAuthSessionMaxPerUser' instead has its own oldest session evicted
    and still receives a token.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | LoginResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            x_request_id=x_request_id,
        )
    ).parsed
