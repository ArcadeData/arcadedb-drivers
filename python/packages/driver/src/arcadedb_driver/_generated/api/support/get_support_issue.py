from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.get_support_issue_response_200 import GetSupportIssueResponse200
from ...types import Response


def _get_kwargs(
    number: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/server/support/issues/{number}".format(
            number=quote(str(number), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | GetSupportIssueResponse200 | None:
    if response.status_code == 200:
        response_200 = GetSupportIssueResponse200.from_dict(response.json())

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
) -> Response[ErrorResponse | GetSupportIssueResponse200]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    number: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ErrorResponse | GetSupportIssueResponse200]:
    """Read a support issue

     Proxy of the portal issue with its public timeline. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | GetSupportIssueResponse200]
    """

    kwargs = _get_kwargs(
        number=number,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    number: str,
    *,
    client: AuthenticatedClient | Client,
) -> ErrorResponse | GetSupportIssueResponse200 | None:
    """Read a support issue

     Proxy of the portal issue with its public timeline. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | GetSupportIssueResponse200
    """

    return sync_detailed(
        number=number,
        client=client,
    ).parsed


async def asyncio_detailed(
    number: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ErrorResponse | GetSupportIssueResponse200]:
    """Read a support issue

     Proxy of the portal issue with its public timeline. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | GetSupportIssueResponse200]
    """

    kwargs = _get_kwargs(
        number=number,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    number: str,
    *,
    client: AuthenticatedClient | Client,
) -> ErrorResponse | GetSupportIssueResponse200 | None:
    """Read a support issue

     Proxy of the portal issue with its public timeline. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | GetSupportIssueResponse200
    """

    return (
        await asyncio_detailed(
            number=number,
            client=client,
        )
    ).parsed
