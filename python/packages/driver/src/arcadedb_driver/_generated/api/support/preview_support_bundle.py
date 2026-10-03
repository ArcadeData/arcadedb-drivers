from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.support_preview import SupportPreview
from ...models.support_preview_request import SupportPreviewRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SupportPreviewRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server/support/preview",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | SupportPreview | None:
    if response.status_code == 200:
        response_200 = SupportPreview.from_dict(response.json())

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

    if response.status_code == 413:
        response_413 = ErrorResponse.from_dict(response.json())

        return response_413

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | SupportPreview]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportPreviewRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | SupportPreview]:
    """Build and preview the redacted support bundle

     Collects the logs of a time window, the diagnostics snapshot and optionally a thread dump into a
    temporary directory, with secrets redacted BEFORE anything is written, and describes them: files,
    sizes, line counts and redaction counts per file, warnings. The preview lives 15 minutes; POST
    /server/support/issues sends exactly these files and POST /server/support/bundle downloads them. Log
    lines carry no time zone: they are written in the time zone of the server JVM, reported in
    'logTimeZone', and the window is converted to it. An empty window is reported in 'warnings', not as
    an error; a window over 100 MB zipped is refused with 413 bundle_too_large. Works without
    registration. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPreviewRequest): What to put in the bundle

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SupportPreview]
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
    body: SupportPreviewRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | SupportPreview | None:
    """Build and preview the redacted support bundle

     Collects the logs of a time window, the diagnostics snapshot and optionally a thread dump into a
    temporary directory, with secrets redacted BEFORE anything is written, and describes them: files,
    sizes, line counts and redaction counts per file, warnings. The preview lives 15 minutes; POST
    /server/support/issues sends exactly these files and POST /server/support/bundle downloads them. Log
    lines carry no time zone: they are written in the time zone of the server JVM, reported in
    'logTimeZone', and the window is converted to it. An empty window is reported in 'warnings', not as
    an error; a window over 100 MB zipped is refused with 413 bundle_too_large. Works without
    registration. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPreviewRequest): What to put in the bundle

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SupportPreview
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportPreviewRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | SupportPreview]:
    """Build and preview the redacted support bundle

     Collects the logs of a time window, the diagnostics snapshot and optionally a thread dump into a
    temporary directory, with secrets redacted BEFORE anything is written, and describes them: files,
    sizes, line counts and redaction counts per file, warnings. The preview lives 15 minutes; POST
    /server/support/issues sends exactly these files and POST /server/support/bundle downloads them. Log
    lines carry no time zone: they are written in the time zone of the server JVM, reported in
    'logTimeZone', and the window is converted to it. An empty window is reported in 'warnings', not as
    an error; a window over 100 MB zipped is refused with 413 bundle_too_large. Works without
    registration. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPreviewRequest): What to put in the bundle

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SupportPreview]
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
    body: SupportPreviewRequest,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | SupportPreview | None:
    """Build and preview the redacted support bundle

     Collects the logs of a time window, the diagnostics snapshot and optionally a thread dump into a
    temporary directory, with secrets redacted BEFORE anything is written, and describes them: files,
    sizes, line counts and redaction counts per file, warnings. The preview lives 15 minutes; POST
    /server/support/issues sends exactly these files and POST /server/support/bundle downloads them. Log
    lines carry no time zone: they are written in the time zone of the server JVM, reported in
    'logTimeZone', and the window is converted to it. An empty window is reported in 'warnings', not as
    an error; a window over 100 MB zipped is refused with 413 bundle_too_large. Works without
    registration. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPreviewRequest): What to put in the bundle

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SupportPreview
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
