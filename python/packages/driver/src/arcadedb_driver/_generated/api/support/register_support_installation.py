from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
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
        "url": "/api/v1/server/support/installation",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = cast(Any, None)
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

    if response.status_code == 503:
        response_503 = ErrorResponse.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | ErrorResponse]:
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
) -> Response[Any | ErrorResponse]:
    """Register this server as an installation in the portal

     Sends the redacted diagnostics of this server to the portal, which creates the installation in the
    workspace of the Client key, or completes the blank fields of the one it already has. Answers
    {status: created|updated|unchanged, installationId, name, filled, differs}. Restricted to the root
    user. Errors carry a code in 'error' (invalid_key, client_mismatch, scope_denied,
    support_not_active, not_found, too_large, rate_limited, bad_request, portal_unreachable,
    portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy, support_stopped)
    and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorResponse]
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
) -> Any | ErrorResponse | None:
    """Register this server as an installation in the portal

     Sends the redacted diagnostics of this server to the portal, which creates the installation in the
    workspace of the Client key, or completes the blank fields of the one it already has. Answers
    {status: created|updated|unchanged, installationId, name, filled, differs}. Restricted to the root
    user. Errors carry a code in 'error' (invalid_key, client_mismatch, scope_denied,
    support_not_active, not_found, too_large, rate_limited, bad_request, portal_unreachable,
    portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy, support_stopped)
    and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorResponse
    """

    return sync_detailed(
        client=client,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[Any | ErrorResponse]:
    """Register this server as an installation in the portal

     Sends the redacted diagnostics of this server to the portal, which creates the installation in the
    workspace of the Client key, or completes the blank fields of the one it already has. Answers
    {status: created|updated|unchanged, installationId, name, filled, differs}. Restricted to the root
    user. Errors carry a code in 'error' (invalid_key, client_mismatch, scope_denied,
    support_not_active, not_found, too_large, rate_limited, bad_request, portal_unreachable,
    portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy, support_stopped)
    and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorResponse]
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
) -> Any | ErrorResponse | None:
    """Register this server as an installation in the portal

     Sends the redacted diagnostics of this server to the portal, which creates the installation in the
    workspace of the Client key, or completes the blank fields of the one it already has. Answers
    {status: created|updated|unchanged, installationId, name, filled, differs}. Restricted to the root
    user. Errors carry a code in 'error' (invalid_key, client_mismatch, scope_denied,
    support_not_active, not_found, too_large, rate_limited, bad_request, portal_unreachable,
    portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy, support_stopped)
    and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            x_request_id=x_request_id,
        )
    ).parsed
