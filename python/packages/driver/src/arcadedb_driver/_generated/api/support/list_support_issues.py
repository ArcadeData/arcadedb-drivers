from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.list_support_issues_response_200 import ListSupportIssuesResponse200
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    status: str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["status"] = status

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/server/support/issues",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | ListSupportIssuesResponse200 | None:
    if response.status_code == 200:
        response_200 = ListSupportIssuesResponse200.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 402:
        response_402 = ErrorResponse.from_dict(response.json())

        return response_402

    if response.status_code == 403:
        response_403 = ErrorResponse.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = ErrorResponse.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 413:
        response_413 = ErrorResponse.from_dict(response.json())

        return response_413

    if response.status_code == 429:
        response_429 = ErrorResponse.from_dict(response.json())

        return response_429

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
) -> Response[ErrorResponse | ListSupportIssuesResponse200]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = UNSET,
) -> Response[ErrorResponse | ListSupportIssuesResponse200]:
    """List the support issues of the workspace

     Proxy of the portal list (only public timeline data). The body is the portal's, unchanged, with the
    Client key scrubbed. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        status (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ListSupportIssuesResponse200]
    """

    kwargs = _get_kwargs(
        status=status,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = UNSET,
) -> ErrorResponse | ListSupportIssuesResponse200 | None:
    """List the support issues of the workspace

     Proxy of the portal list (only public timeline data). The body is the portal's, unchanged, with the
    Client key scrubbed. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        status (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ListSupportIssuesResponse200
    """

    return sync_detailed(
        client=client,
        status=status,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = UNSET,
) -> Response[ErrorResponse | ListSupportIssuesResponse200]:
    """List the support issues of the workspace

     Proxy of the portal list (only public timeline data). The body is the portal's, unchanged, with the
    Client key scrubbed. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        status (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | ListSupportIssuesResponse200]
    """

    kwargs = _get_kwargs(
        status=status,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    status: str | Unset = UNSET,
) -> ErrorResponse | ListSupportIssuesResponse200 | None:
    """List the support issues of the workspace

     Proxy of the portal list (only public timeline data). The body is the portal's, unchanged, with the
    Client key scrubbed. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        status (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | ListSupportIssuesResponse200
    """

    return (
        await asyncio_detailed(
            client=client,
            status=status,
        )
    ).parsed
