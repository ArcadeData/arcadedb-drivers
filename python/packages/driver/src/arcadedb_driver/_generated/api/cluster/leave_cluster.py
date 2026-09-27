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
    force: bool | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    params: dict[str, Any] = {}

    params["force"] = force

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cluster/leave",
        "params": params,
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
    force: bool | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Leave the cluster

     Removes this server from the Raft configuration. Answers 409 when leaving would break quorum, unless
    'force' is set.Requires RaftHAPlugin: the route is registered on every server, but answers only
    where high availability is configured.

    Args:
        force (bool | Unset):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        force=force,
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    force: bool | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ClusterActionResponse | ErrorResponse | None:
    """Leave the cluster

     Removes this server from the Raft configuration. Answers 409 when leaving would break quorum, unless
    'force' is set.Requires RaftHAPlugin: the route is registered on every server, but answers only
    where high availability is configured.

    Args:
        force (bool | Unset):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        force=force,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    force: bool | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Leave the cluster

     Removes this server from the Raft configuration. Answers 409 when leaving would break quorum, unless
    'force' is set.Requires RaftHAPlugin: the route is registered on every server, but answers only
    where high availability is configured.

    Args:
        force (bool | Unset):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        force=force,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    force: bool | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ClusterActionResponse | ErrorResponse | None:
    """Leave the cluster

     Removes this server from the Raft configuration. Answers 409 when leaving would break quorum, unless
    'force' is set.Requires RaftHAPlugin: the route is registered on every server, but answers only
    where high availability is configured.

    Args:
        force (bool | Unset):
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
            force=force,
            x_request_id=x_request_id,
        )
    ).parsed
