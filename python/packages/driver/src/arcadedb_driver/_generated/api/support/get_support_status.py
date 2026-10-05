from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.support_status import SupportStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    refresh: str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["refresh"] = refresh

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/server/support",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | SupportStatus | None:
    if response.status_code == 200:
        response_200 = SupportStatus.from_dict(response.json())

        return response_200

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
) -> Response[ErrorResponse | SupportStatus]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    refresh: str | Unset = UNSET,
) -> Response[ErrorResponse | SupportStatus]:
    """Read the support registration of this server

     Whether the server is registered with the ArcadeData customer portal, and the workspace, plan and
    first-response times the portal reports. The Client key is never returned, only its last four
    characters ('keyHint'). Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        refresh (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SupportStatus]
    """

    kwargs = _get_kwargs(
        refresh=refresh,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    refresh: str | Unset = UNSET,
) -> ErrorResponse | SupportStatus | None:
    """Read the support registration of this server

     Whether the server is registered with the ArcadeData customer portal, and the workspace, plan and
    first-response times the portal reports. The Client key is never returned, only its last four
    characters ('keyHint'). Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        refresh (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SupportStatus
    """

    return sync_detailed(
        client=client,
        refresh=refresh,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    refresh: str | Unset = UNSET,
) -> Response[ErrorResponse | SupportStatus]:
    """Read the support registration of this server

     Whether the server is registered with the ArcadeData customer portal, and the workspace, plan and
    first-response times the portal reports. The Client key is never returned, only its last four
    characters ('keyHint'). Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        refresh (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SupportStatus]
    """

    kwargs = _get_kwargs(
        refresh=refresh,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    refresh: str | Unset = UNSET,
) -> ErrorResponse | SupportStatus | None:
    """Read the support registration of this server

     Whether the server is registered with the ArcadeData customer portal, and the workspace, plan and
    first-response times the portal reports. The Client key is never returned, only its last four
    characters ('keyHint'). Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        refresh (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SupportStatus
    """

    return (
        await asyncio_detailed(
            client=client,
            refresh=refresh,
        )
    ).parsed
