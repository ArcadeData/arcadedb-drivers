from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ai_activate_request import AiActivateRequest
from ...models.ai_activate_response import AiActivateResponse
from ...models.error_response import ErrorResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: AiActivateRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/ai/activate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AiActivateResponse | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = AiActivateResponse.from_dict(response.json())

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

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if response.status_code == 502:
        response_502 = ErrorResponse.from_dict(response.json())

        return response_502

    if response.status_code == 503:
        response_503 = ErrorResponse.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[AiActivateResponse | ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AiActivateRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[AiActivateResponse | ErrorResponse]:
    """Activate the AI assistant with a subscription key

     Exchanges a subscription key for an activation held by the server. The server sends its version and
    a derived hardware id to the gateway as part of the exchange, and restricts this operation to the
    root user because it writes server-wide configuration (config/ai.json).

    Args:
        x_request_id (str | Unset):
        body (AiActivateRequest): Activation request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AiActivateResponse | ErrorResponse]
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
    body: AiActivateRequest,
    x_request_id: str | Unset = UNSET,
) -> AiActivateResponse | ErrorResponse | None:
    """Activate the AI assistant with a subscription key

     Exchanges a subscription key for an activation held by the server. The server sends its version and
    a derived hardware id to the gateway as part of the exchange, and restricts this operation to the
    root user because it writes server-wide configuration (config/ai.json).

    Args:
        x_request_id (str | Unset):
        body (AiActivateRequest): Activation request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AiActivateResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AiActivateRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[AiActivateResponse | ErrorResponse]:
    """Activate the AI assistant with a subscription key

     Exchanges a subscription key for an activation held by the server. The server sends its version and
    a derived hardware id to the gateway as part of the exchange, and restricts this operation to the
    root user because it writes server-wide configuration (config/ai.json).

    Args:
        x_request_id (str | Unset):
        body (AiActivateRequest): Activation request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AiActivateResponse | ErrorResponse]
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
    body: AiActivateRequest,
    x_request_id: str | Unset = UNSET,
) -> AiActivateResponse | ErrorResponse | None:
    """Activate the AI assistant with a subscription key

     Exchanges a subscription key for an activation held by the server. The server sends its version and
    a derived hardware id to the gateway as part of the exchange, and restricts this operation to the
    root user because it writes server-wide configuration (config/ai.json).

    Args:
        x_request_id (str | Unset):
        body (AiActivateRequest): Activation request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AiActivateResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
