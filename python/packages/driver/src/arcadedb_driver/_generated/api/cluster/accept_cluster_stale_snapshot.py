from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cluster_action_response import ClusterActionResponse
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
        "url": "/api/v1/cluster/accept-stale-snapshot",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ClusterActionResponse | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = ClusterActionResponse.from_dict(response.json())

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

    if response.status_code == 404:
        response_404 = ErrorResponse.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ClusterActionResponse | ErrorResponse]:
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
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Lift the node-wide stale-snapshot read floor no peer can resync

     Lifts the node-wide stale-snapshot read floor, accepting this node's databases as they are without a
    resync. The floor stands while the replication snapshot marker runs ahead of the entries this node
    applied: the node reports not-ready and LINEARIZABLE reads are clamped until a full resync from a
    peer fills the gap. A leader cannot resync from itself, so on a node that is the only voter of its
    cluster the floor never lifts. The entries between the floor and the marker are NOT replayed: if a
    database is missing them, it stays missing. The marker index is persisted as the applied position,
    so a restart does not raise the floor again, and the change is logged with who made it, the floor
    and the marker index. A database quarantined on its own keeps its quarantine (see accept-diverged).
    Root only. Answers 404 when no floor stands, and 409 on a node that is not the sole voter, where the
    resync is the way out, or while a snapshot download is running. The body is ignored. Requires
    RaftHAPlugin: the route is registered on every server, but answers only where high availability is
    configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
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
) -> ClusterActionResponse | ErrorResponse | None:
    """Lift the node-wide stale-snapshot read floor no peer can resync

     Lifts the node-wide stale-snapshot read floor, accepting this node's databases as they are without a
    resync. The floor stands while the replication snapshot marker runs ahead of the entries this node
    applied: the node reports not-ready and LINEARIZABLE reads are clamped until a full resync from a
    peer fills the gap. A leader cannot resync from itself, so on a node that is the only voter of its
    cluster the floor never lifts. The entries between the floor and the marker are NOT replayed: if a
    database is missing them, it stays missing. The marker index is persisted as the applied position,
    so a restart does not raise the floor again, and the change is logged with who made it, the floor
    and the marker index. A database quarantined on its own keeps its quarantine (see accept-diverged).
    Root only. Answers 404 when no floor stands, and 409 on a node that is not the sole voter, where the
    resync is the way out, or while a snapshot download is running. The body is ignored. Requires
    RaftHAPlugin: the route is registered on every server, but answers only where high availability is
    configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Lift the node-wide stale-snapshot read floor no peer can resync

     Lifts the node-wide stale-snapshot read floor, accepting this node's databases as they are without a
    resync. The floor stands while the replication snapshot marker runs ahead of the entries this node
    applied: the node reports not-ready and LINEARIZABLE reads are clamped until a full resync from a
    peer fills the gap. A leader cannot resync from itself, so on a node that is the only voter of its
    cluster the floor never lifts. The entries between the floor and the marker are NOT replayed: if a
    database is missing them, it stays missing. The marker index is persisted as the applied position,
    so a restart does not raise the floor again, and the change is logged with who made it, the floor
    and the marker index. A database quarantined on its own keeps its quarantine (see accept-diverged).
    Root only. Answers 404 when no floor stands, and 409 on a node that is not the sole voter, where the
    resync is the way out, or while a snapshot download is running. The body is ignored. Requires
    RaftHAPlugin: the route is registered on every server, but answers only where high availability is
    configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
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
) -> ClusterActionResponse | ErrorResponse | None:
    """Lift the node-wide stale-snapshot read floor no peer can resync

     Lifts the node-wide stale-snapshot read floor, accepting this node's databases as they are without a
    resync. The floor stands while the replication snapshot marker runs ahead of the entries this node
    applied: the node reports not-ready and LINEARIZABLE reads are clamped until a full resync from a
    peer fills the gap. A leader cannot resync from itself, so on a node that is the only voter of its
    cluster the floor never lifts. The entries between the floor and the marker are NOT replayed: if a
    database is missing them, it stays missing. The marker index is persisted as the applied position,
    so a restart does not raise the floor again, and the change is logged with who made it, the floor
    and the marker index. A database quarantined on its own keeps its quarantine (see accept-diverged).
    Root only. Answers 404 when no floor stands, and 409 on a node that is not the sole voter, where the
    resync is the way out, or while a snapshot download is running. The body is ignored. Requires
    RaftHAPlugin: the route is registered on every server, but answers only where high availability is
    configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            x_request_id=x_request_id,
        )
    ).parsed
