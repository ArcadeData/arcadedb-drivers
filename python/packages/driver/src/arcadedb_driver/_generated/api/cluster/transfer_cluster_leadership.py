from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cluster_action_response import ClusterActionResponse
from ...models.error_response import ErrorResponse
from ...models.transfer_leader_request import TransferLeaderRequest
from ...types import Response


def _get_kwargs(
    *,
    body: TransferLeaderRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cluster/leader",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

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
    body: TransferLeaderRequest,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Transfer leadership

     Transfers Raft leadership, to the named peer when 'peerId' is given and to whichever peer Raft
    selects otherwise. Unknown fields in the body are rejected. Only the leader can transfer leadership:
    a server that is not the leader answers 409 naming the leader to reissue against, rather than
    routing the request there and forcing an election nobody asked for.Requires RaftHAPlugin: the route
    is registered on every server, but answers only where high availability is configured.

    Args:
        body (TransferLeaderRequest): Transfer target. Send an empty object to let Raft choose.
            Unknown fields are rejected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: TransferLeaderRequest,
) -> ClusterActionResponse | ErrorResponse | None:
    """Transfer leadership

     Transfers Raft leadership, to the named peer when 'peerId' is given and to whichever peer Raft
    selects otherwise. Unknown fields in the body are rejected. Only the leader can transfer leadership:
    a server that is not the leader answers 409 naming the leader to reissue against, rather than
    routing the request there and forcing an election nobody asked for.Requires RaftHAPlugin: the route
    is registered on every server, but answers only where high availability is configured.

    Args:
        body (TransferLeaderRequest): Transfer target. Send an empty object to let Raft choose.
            Unknown fields are rejected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: TransferLeaderRequest,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Transfer leadership

     Transfers Raft leadership, to the named peer when 'peerId' is given and to whichever peer Raft
    selects otherwise. Unknown fields in the body are rejected. Only the leader can transfer leadership:
    a server that is not the leader answers 409 naming the leader to reissue against, rather than
    routing the request there and forcing an election nobody asked for.Requires RaftHAPlugin: the route
    is registered on every server, but answers only where high availability is configured.

    Args:
        body (TransferLeaderRequest): Transfer target. Send an empty object to let Raft choose.
            Unknown fields are rejected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: TransferLeaderRequest,
) -> ClusterActionResponse | ErrorResponse | None:
    """Transfer leadership

     Transfers Raft leadership, to the named peer when 'peerId' is given and to whichever peer Raft
    selects otherwise. Unknown fields in the body are rejected. Only the leader can transfer leadership:
    a server that is not the leader answers 409 naming the leader to reissue against, rather than
    routing the request there and forcing an election nobody asked for.Requires RaftHAPlugin: the route
    is registered on every server, but answers only where high availability is configured.

    Args:
        body (TransferLeaderRequest): Transfer target. Send an empty object to let Raft choose.
            Unknown fields are rejected.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
