from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.answer_support_request_response_201 import AnswerSupportRequestResponse201
from ...models.error_response import ErrorResponse
from ...models.support_answer_request import SupportAnswerRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    number: str,
    request_id: str,
    *,
    body: SupportAnswerRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server/support/issues/{number}/requests/{request_id}/response".format(
            number=quote(str(number), safe=""),
            request_id=quote(str(request_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AnswerSupportRequestResponse201 | ErrorResponse | None:
    if response.status_code == 201:
        response_201 = AnswerSupportRequestResponse201.from_dict(response.json())

        return response_201

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
) -> Response[AnswerSupportRequestResponse201 | ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    number: str,
    request_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: SupportAnswerRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[AnswerSupportRequestResponse201 | ErrorResponse]:
    """Answer a support request

     Staff can ask for the result of a read-only query. The browser runs it through the ordinary query
    endpoint, then sends the result (or a decline, or the failure) here and the server forwards it to
    the portal, which turns it into a client comment. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):
        request_id (str):
        x_request_id (str | Unset):
        body (SupportAnswerRequest): The answer to a support request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AnswerSupportRequestResponse201 | ErrorResponse]
    """

    kwargs = _get_kwargs(
        number=number,
        request_id=request_id,
        body=body,
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    number: str,
    request_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: SupportAnswerRequest,
    x_request_id: str | Unset = UNSET,
) -> AnswerSupportRequestResponse201 | ErrorResponse | None:
    """Answer a support request

     Staff can ask for the result of a read-only query. The browser runs it through the ordinary query
    endpoint, then sends the result (or a decline, or the failure) here and the server forwards it to
    the portal, which turns it into a client comment. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):
        request_id (str):
        x_request_id (str | Unset):
        body (SupportAnswerRequest): The answer to a support request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AnswerSupportRequestResponse201 | ErrorResponse
    """

    return sync_detailed(
        number=number,
        request_id=request_id,
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    number: str,
    request_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: SupportAnswerRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[AnswerSupportRequestResponse201 | ErrorResponse]:
    """Answer a support request

     Staff can ask for the result of a read-only query. The browser runs it through the ordinary query
    endpoint, then sends the result (or a decline, or the failure) here and the server forwards it to
    the portal, which turns it into a client comment. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):
        request_id (str):
        x_request_id (str | Unset):
        body (SupportAnswerRequest): The answer to a support request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AnswerSupportRequestResponse201 | ErrorResponse]
    """

    kwargs = _get_kwargs(
        number=number,
        request_id=request_id,
        body=body,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    number: str,
    request_id: str,
    *,
    client: AuthenticatedClient | Client,
    body: SupportAnswerRequest,
    x_request_id: str | Unset = UNSET,
) -> AnswerSupportRequestResponse201 | ErrorResponse | None:
    """Answer a support request

     Staff can ask for the result of a read-only query. The browser runs it through the ordinary query
    endpoint, then sends the result (or a decline, or the failure) here and the server forwards it to
    the portal, which turns it into a client comment. Restricted to the root user. Errors carry a code
    in 'error' (invalid_key, client_mismatch, scope_denied, support_not_active, not_found, too_large,
    rate_limited, bad_request, portal_unreachable, portal_error, not_registered, preview_not_found,
    bundle_too_large, preview_busy, support_stopped) and a clear message in 'message'.

    Args:
        number (str):
        request_id (str):
        x_request_id (str | Unset):
        body (SupportAnswerRequest): The answer to a support request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AnswerSupportRequestResponse201 | ErrorResponse
    """

    return (
        await asyncio_detailed(
            number=number,
            request_id=request_id,
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
