from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.support_bundle_request import SupportBundleRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SupportBundleRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server/support/bundle",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ErrorResponse | None:
    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = ErrorResponse.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = ErrorResponse.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportBundleRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse]:
    """Download the redacted support bundle

     Streams the files of a preview as one zip (logs under logs/, diagnostics.json, summary.json,
    threads.txt): for the public GitHub path and offline sharing. Nothing is uploaded anywhere.
    Restricted to the root user.

    Args:
        x_request_id (str | Unset):
        body (SupportBundleRequest): The preview to download

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse]
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
    body: SupportBundleRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | None:
    """Download the redacted support bundle

     Streams the files of a preview as one zip (logs under logs/, diagnostics.json, summary.json,
    threads.txt): for the public GitHub path and offline sharing. Nothing is uploaded anywhere.
    Restricted to the root user.

    Args:
        x_request_id (str | Unset):
        body (SupportBundleRequest): The preview to download

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportBundleRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse]:
    """Download the redacted support bundle

     Streams the files of a preview as one zip (logs under logs/, diagnostics.json, summary.json,
    threads.txt): for the public GitHub path and offline sharing. Nothing is uploaded anywhere.
    Restricted to the root user.

    Args:
        x_request_id (str | Unset):
        body (SupportBundleRequest): The preview to download

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse]
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
    body: SupportBundleRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | None:
    """Download the redacted support bundle

     Streams the files of a preview as one zip (logs under logs/, diagnostics.json, summary.json,
    threads.txt): for the public GitHub path and offline sharing. Nothing is uploaded anywhere.
    Restricted to the root user.

    Args:
        x_request_id (str | Unset):
        body (SupportBundleRequest): The preview to download

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
