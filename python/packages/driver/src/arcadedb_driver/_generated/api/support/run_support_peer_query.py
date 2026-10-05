from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.support_peer_query_request import SupportPeerQueryRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SupportPeerQueryRequest,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/server/support/peer-query",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = cast(Any, None)
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
    body: SupportPeerQueryRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[Any | ErrorResponse]:
    """Run a read-only support query on other cluster nodes

     Runs the statement of a support request on the OTHER members of the cluster ('all' or one named
    node) and answers {ha, nodes: [{node, status: ok, records, truncated} | {node, status: failed,
    error}]}: a peer that cannot be reached, times out or refuses is its own row and never fails the
    request. The node that receives this call does not run the query on itself: Studio does that through
    the ordinary query endpoint. Each peer runs the statement through its ordinary idempotent query
    endpoint, so the engine of EACH peer refuses anything that is not read-only; peers are chosen from
    the cluster configuration by name, never by address, and the query runs on the peer with the
    permissions of the calling user. At most 16 peers, 8 at a time, 35 seconds and 4 MB each; SQL and
    OpenCypher only. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPeerQueryRequest): A read-only query to run on other cluster nodes

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorResponse]
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
    body: SupportPeerQueryRequest,
    x_request_id: str | Unset = UNSET,
) -> Any | ErrorResponse | None:
    """Run a read-only support query on other cluster nodes

     Runs the statement of a support request on the OTHER members of the cluster ('all' or one named
    node) and answers {ha, nodes: [{node, status: ok, records, truncated} | {node, status: failed,
    error}]}: a peer that cannot be reached, times out or refuses is its own row and never fails the
    request. The node that receives this call does not run the query on itself: Studio does that through
    the ordinary query endpoint. Each peer runs the statement through its ordinary idempotent query
    endpoint, so the engine of EACH peer refuses anything that is not read-only; peers are chosen from
    the cluster configuration by name, never by address, and the query runs on the peer with the
    permissions of the calling user. At most 16 peers, 8 at a time, 35 seconds and 4 MB each; SQL and
    OpenCypher only. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPeerQueryRequest): A read-only query to run on other cluster nodes

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SupportPeerQueryRequest,
    x_request_id: str | Unset = UNSET,
) -> Response[Any | ErrorResponse]:
    """Run a read-only support query on other cluster nodes

     Runs the statement of a support request on the OTHER members of the cluster ('all' or one named
    node) and answers {ha, nodes: [{node, status: ok, records, truncated} | {node, status: failed,
    error}]}: a peer that cannot be reached, times out or refuses is its own row and never fails the
    request. The node that receives this call does not run the query on itself: Studio does that through
    the ordinary query endpoint. Each peer runs the statement through its ordinary idempotent query
    endpoint, so the engine of EACH peer refuses anything that is not read-only; peers are chosen from
    the cluster configuration by name, never by address, and the query runs on the peer with the
    permissions of the calling user. At most 16 peers, 8 at a time, 35 seconds and 4 MB each; SQL and
    OpenCypher only. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPeerQueryRequest): A read-only query to run on other cluster nodes

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorResponse]
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
    body: SupportPeerQueryRequest,
    x_request_id: str | Unset = UNSET,
) -> Any | ErrorResponse | None:
    """Run a read-only support query on other cluster nodes

     Runs the statement of a support request on the OTHER members of the cluster ('all' or one named
    node) and answers {ha, nodes: [{node, status: ok, records, truncated} | {node, status: failed,
    error}]}: a peer that cannot be reached, times out or refuses is its own row and never fails the
    request. The node that receives this call does not run the query on itself: Studio does that through
    the ordinary query endpoint. Each peer runs the statement through its ordinary idempotent query
    endpoint, so the engine of EACH peer refuses anything that is not read-only; peers are chosen from
    the cluster configuration by name, never by address, and the query runs on the peer with the
    permissions of the calling user. At most 16 peers, 8 at a time, 35 seconds and 4 MB each; SQL and
    OpenCypher only. Restricted to the root user. Errors carry a code in 'error' (invalid_key,
    client_mismatch, scope_denied, support_not_active, not_found, too_large, rate_limited, bad_request,
    portal_unreachable, portal_error, not_registered, preview_not_found, bundle_too_large, preview_busy,
    support_stopped) and a clear message in 'message'.

    Args:
        x_request_id (str | Unset):
        body (SupportPeerQueryRequest): A read-only query to run on other cluster nodes

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
