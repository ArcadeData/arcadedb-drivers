from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.peer_capabilities_response import PeerCapabilitiesResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cluster/capabilities",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | PeerCapabilitiesResponse | None:
    if response.status_code == 200:
        response_200 = PeerCapabilitiesResponse.from_dict(response.json())

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

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | PeerCapabilitiesResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ErrorResponse | PeerCapabilitiesResponse]:
    """Report the wire-format capabilities of this peer

     Reports the optional replication wire-format sections this node can DECODE, as short stable tokens.
    The leader polls it on every peer of its Raft configuration and writes an optional section only when
    every peer has advertised it, so a rolling upgrade needs no ordering by hand (issue #7219).

    A node running a release without this route answers 404, and the caller reads that as 'this peer can
    decode nothing optional' - which is why the route is safe to add and why no version comparison takes
    part in the decision.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | PeerCapabilitiesResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> ErrorResponse | PeerCapabilitiesResponse | None:
    """Report the wire-format capabilities of this peer

     Reports the optional replication wire-format sections this node can DECODE, as short stable tokens.
    The leader polls it on every peer of its Raft configuration and writes an optional section only when
    every peer has advertised it, so a rolling upgrade needs no ordering by hand (issue #7219).

    A node running a release without this route answers 404, and the caller reads that as 'this peer can
    decode nothing optional' - which is why the route is safe to add and why no version comparison takes
    part in the decision.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | PeerCapabilitiesResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ErrorResponse | PeerCapabilitiesResponse]:
    """Report the wire-format capabilities of this peer

     Reports the optional replication wire-format sections this node can DECODE, as short stable tokens.
    The leader polls it on every peer of its Raft configuration and writes an optional section only when
    every peer has advertised it, so a rolling upgrade needs no ordering by hand (issue #7219).

    A node running a release without this route answers 404, and the caller reads that as 'this peer can
    decode nothing optional' - which is why the route is safe to add and why no version comparison takes
    part in the decision.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | PeerCapabilitiesResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> ErrorResponse | PeerCapabilitiesResponse | None:
    """Report the wire-format capabilities of this peer

     Reports the optional replication wire-format sections this node can DECODE, as short stable tokens.
    The leader polls it on every peer of its Raft configuration and writes an optional section only when
    every peer has advertised it, so a rolling upgrade needs no ordering by hand (issue #7219).

    A node running a release without this route answers 404, and the caller reads that as 'this peer can
    decode nothing optional' - which is why the route is safe to add and why no version comparison takes
    part in the decision.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | PeerCapabilitiesResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
