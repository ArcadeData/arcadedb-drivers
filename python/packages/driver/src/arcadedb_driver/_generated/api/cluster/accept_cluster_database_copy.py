from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cluster_action_response import ClusterActionResponse
from ...models.error_response import ErrorResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cluster/accept-copy/{database}".format(
            database=quote(str(database), safe=""),
        ),
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
    database: str,
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Accept the leader's unverified copy of a database

     Accepts this leader's closed copy of one database, which the last resync could not verify, as the
    cluster's copy without the other servers' confirmation. Before reopening such a copy the leader asks
    every peer about its own, and refuses while any peer is unanswered or holds a copy that cannot be
    ordered (the critical unverified-closed-copy-refused alert); a peer that can never answer again
    keeps the database closed on every node. This override removes the copy's marker and logs who
    accepted it, at which applied index, over which refusal. The copy is not reopened by this call: the
    next request that names the database reopens it, and every follower then installs it. Root only.
    Answers 400 on a follower, and 404 when this server holds no closed copy of the database marked
    unverified. The body is ignored.Requires RaftHAPlugin: the route is registered on every server, but
    answers only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> ClusterActionResponse | ErrorResponse | None:
    """Accept the leader's unverified copy of a database

     Accepts this leader's closed copy of one database, which the last resync could not verify, as the
    cluster's copy without the other servers' confirmation. Before reopening such a copy the leader asks
    every peer about its own, and refuses while any peer is unanswered or holds a copy that cannot be
    ordered (the critical unverified-closed-copy-refused alert); a peer that can never answer again
    keeps the database closed on every node. This override removes the copy's marker and logs who
    accepted it, at which applied index, over which refusal. The copy is not reopened by this call: the
    next request that names the database reopens it, and every follower then installs it. Root only.
    Answers 400 on a follower, and 404 when this server holds no closed copy of the database marked
    unverified. The body is ignored.Requires RaftHAPlugin: the route is registered on every server, but
    answers only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> Response[ClusterActionResponse | ErrorResponse]:
    """Accept the leader's unverified copy of a database

     Accepts this leader's closed copy of one database, which the last resync could not verify, as the
    cluster's copy without the other servers' confirmation. Before reopening such a copy the leader asks
    every peer about its own, and refuses while any peer is unanswered or holds a copy that cannot be
    ordered (the critical unverified-closed-copy-refused alert); a peer that can never answer again
    keeps the database closed on every node. This override removes the copy's marker and logs who
    accepted it, at which applied index, over which refusal. The copy is not reopened by this call: the
    next request that names the database reopens it, and every follower then installs it. Root only.
    Answers 400 on a follower, and 404 when this server holds no closed copy of the database marked
    unverified. The body is ignored.Requires RaftHAPlugin: the route is registered on every server, but
    answers only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClusterActionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    x_request_id: str | Unset = UNSET,
) -> ClusterActionResponse | ErrorResponse | None:
    """Accept the leader's unverified copy of a database

     Accepts this leader's closed copy of one database, which the last resync could not verify, as the
    cluster's copy without the other servers' confirmation. Before reopening such a copy the leader asks
    every peer about its own, and refuses while any peer is unanswered or holds a copy that cannot be
    ordered (the critical unverified-closed-copy-refused alert); a peer that can never answer again
    keeps the database closed on every node. This override removes the copy's marker and logs who
    accepted it, at which applied index, over which refusal. The copy is not reopened by this call: the
    next request that names the database reopens it, and every follower then installs it. Root only.
    Answers 400 on a follower, and 404 when this server holds no closed copy of the database marked
    unverified. The body is ignored.Requires RaftHAPlugin: the route is registered on every server, but
    answers only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClusterActionResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            x_request_id=x_request_id,
        )
    ).parsed
