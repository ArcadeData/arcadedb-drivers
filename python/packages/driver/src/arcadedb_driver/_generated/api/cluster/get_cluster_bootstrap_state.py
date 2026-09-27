from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.bootstrap_state_response import BootstrapStateResponse
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
        "url": "/api/v1/cluster/bootstrap-state",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> BootstrapStateResponse | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = BootstrapStateResponse.from_dict(response.json())

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
) -> Response[BootstrapStateResponse | ErrorResponse]:
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
) -> Response[BootstrapStateResponse | ErrorResponse]:
    """Report per-database bootstrap state

     Reports this peer's fingerprint and last transaction id for every database. Used by the bootstrap
    leader at first cluster formation to decide which copy of each database wins. A database this peer
    cannot read is reported with an 'error' and a last transaction id of -1 rather than omitted.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BootstrapStateResponse | ErrorResponse]
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
) -> BootstrapStateResponse | ErrorResponse | None:
    """Report per-database bootstrap state

     Reports this peer's fingerprint and last transaction id for every database. Used by the bootstrap
    leader at first cluster formation to decide which copy of each database wins. A database this peer
    cannot read is reported with an 'error' and a last transaction id of -1 rather than omitted.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BootstrapStateResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[BootstrapStateResponse | ErrorResponse]:
    """Report per-database bootstrap state

     Reports this peer's fingerprint and last transaction id for every database. Used by the bootstrap
    leader at first cluster formation to decide which copy of each database wins. A database this peer
    cannot read is reported with an 'error' and a last transaction id of -1 rather than omitted.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BootstrapStateResponse | ErrorResponse]
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
) -> BootstrapStateResponse | ErrorResponse | None:
    """Report per-database bootstrap state

     Reports this peer's fingerprint and last transaction id for every database. Used by the bootstrap
    leader at first cluster formation to decide which copy of each database wins. A database this peer
    cannot read is reported with an 'error' and a last transaction id of -1 rather than omitted.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BootstrapStateResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            x_request_id=x_request_id,
        )
    ).parsed
