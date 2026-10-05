from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.stage_support_screenshot_response_201 import StageSupportScreenshotResponse201
from ...models.support_screenshot_request import SupportScreenshotRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SupportScreenshotRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server/support/screenshots",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | StageSupportScreenshotResponse201 | None:
    if response.status_code == 201:
        response_201 = StageSupportScreenshotResponse201.from_dict(response.json())

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

    if response.status_code == 413:
        response_413 = ErrorResponse.from_dict(response.json())

        return response_413

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | StageSupportScreenshotResponse201]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportScreenshotRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | StageSupportScreenshotResponse201]:
    """Hold a screenshot until it is sent

     A user pastes, drops or picks a picture of what they see (a query result, an error). It is held in
    memory for 15 minutes, checked by its first bytes (PNG, JPEG, GIF or WebP; never SVG), at most 5 MB,
    and answered by id so the issue, the reply or the files can refer to it in `screenshots`. Nothing is
    sent to ArcadeData until then. Restricted to the root user. Errors carry a code in 'error'
    (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited,
    bad_request, portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large,
    preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportScreenshotRequest): A screenshot

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | StageSupportScreenshotResponse201]
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
    body: SupportScreenshotRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | StageSupportScreenshotResponse201 | None:
    """Hold a screenshot until it is sent

     A user pastes, drops or picks a picture of what they see (a query result, an error). It is held in
    memory for 15 minutes, checked by its first bytes (PNG, JPEG, GIF or WebP; never SVG), at most 5 MB,
    and answered by id so the issue, the reply or the files can refer to it in `screenshots`. Nothing is
    sent to ArcadeData until then. Restricted to the root user. Errors carry a code in 'error'
    (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited,
    bad_request, portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large,
    preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportScreenshotRequest): A screenshot

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | StageSupportScreenshotResponse201
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportScreenshotRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | StageSupportScreenshotResponse201]:
    """Hold a screenshot until it is sent

     A user pastes, drops or picks a picture of what they see (a query result, an error). It is held in
    memory for 15 minutes, checked by its first bytes (PNG, JPEG, GIF or WebP; never SVG), at most 5 MB,
    and answered by id so the issue, the reply or the files can refer to it in `screenshots`. Nothing is
    sent to ArcadeData until then. Restricted to the root user. Errors carry a code in 'error'
    (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited,
    bad_request, portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large,
    preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportScreenshotRequest): A screenshot

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | StageSupportScreenshotResponse201]
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
    body: SupportScreenshotRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | StageSupportScreenshotResponse201 | None:
    """Hold a screenshot until it is sent

     A user pastes, drops or picks a picture of what they see (a query result, an error). It is held in
    memory for 15 minutes, checked by its first bytes (PNG, JPEG, GIF or WebP; never SVG), at most 5 MB,
    and answered by id so the issue, the reply or the files can refer to it in `screenshots`. Nothing is
    sent to ArcadeData until then. Restricted to the root user. Errors carry a code in 'error'
    (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited,
    bad_request, portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large,
    preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportScreenshotRequest): A screenshot

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | StageSupportScreenshotResponse201
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
