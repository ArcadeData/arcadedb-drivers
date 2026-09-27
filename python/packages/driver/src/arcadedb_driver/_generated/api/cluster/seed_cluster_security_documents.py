from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.security_seed_request import SecuritySeedRequest
from ...models.security_seed_response import SecuritySeedResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SecuritySeedRequest | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cluster/security-seed",
    }

    if not isinstance(body, Unset):
        _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | SecuritySeedResponse | None:
    if response.status_code == 200:
        response_200 = SecuritySeedResponse.from_dict(response.json())

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

    if response.status_code == 503:
        response_503 = SecuritySeedResponse.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | SecuritySeedResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SecuritySeedRequest | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | SecuritySeedResponse]:
    """Have the leader replicate the cluster security documents

     Asks the Raft LEADER to submit server-users.jsonl, server-groups.json and server-api-tokens.json to
    the cluster, and answers with the ones that did not commit.

    Two callers need it, and both are cluster-internal. A node that has just admitted a peer reads the
    outcome here instead of running a seed of its own, so an admission is seeded once rather than from
    two nodes under two different monitors (issue #7834). A node that came back while it was still a
    Raft member - a rolling restart, a drain and reschedule, a pod whose ordinal is in the static server
    list - sends the fingerprints of the documents it holds, and is re-seeded only if they differ from
    the leader's (issue #7833); the three documents live outside the database directory, so no snapshot
    install carries them.

    Answered 409 by a node that is not the leader, naming the one it believes leads. Answered 503 with
    the failedSeeds array when the seed ran but a document did not commit, which is the same contract
    POST /api/v1/cluster/peer answers with.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):
        body (SecuritySeedRequest | Unset): What the caller wants seeded, and what it already
            holds

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SecuritySeedResponse]
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
    body: SecuritySeedRequest | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | SecuritySeedResponse | None:
    """Have the leader replicate the cluster security documents

     Asks the Raft LEADER to submit server-users.jsonl, server-groups.json and server-api-tokens.json to
    the cluster, and answers with the ones that did not commit.

    Two callers need it, and both are cluster-internal. A node that has just admitted a peer reads the
    outcome here instead of running a seed of its own, so an admission is seeded once rather than from
    two nodes under two different monitors (issue #7834). A node that came back while it was still a
    Raft member - a rolling restart, a drain and reschedule, a pod whose ordinal is in the static server
    list - sends the fingerprints of the documents it holds, and is re-seeded only if they differ from
    the leader's (issue #7833); the three documents live outside the database directory, so no snapshot
    install carries them.

    Answered 409 by a node that is not the leader, naming the one it believes leads. Answered 503 with
    the failedSeeds array when the seed ran but a document did not commit, which is the same contract
    POST /api/v1/cluster/peer answers with.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):
        body (SecuritySeedRequest | Unset): What the caller wants seeded, and what it already
            holds

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SecuritySeedResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SecuritySeedRequest | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | SecuritySeedResponse]:
    """Have the leader replicate the cluster security documents

     Asks the Raft LEADER to submit server-users.jsonl, server-groups.json and server-api-tokens.json to
    the cluster, and answers with the ones that did not commit.

    Two callers need it, and both are cluster-internal. A node that has just admitted a peer reads the
    outcome here instead of running a seed of its own, so an admission is seeded once rather than from
    two nodes under two different monitors (issue #7834). A node that came back while it was still a
    Raft member - a rolling restart, a drain and reschedule, a pod whose ordinal is in the static server
    list - sends the fingerprints of the documents it holds, and is re-seeded only if they differ from
    the leader's (issue #7833); the three documents live outside the database directory, so no snapshot
    install carries them.

    Answered 409 by a node that is not the leader, naming the one it believes leads. Answered 503 with
    the failedSeeds array when the seed ran but a document did not commit, which is the same contract
    POST /api/v1/cluster/peer answers with.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):
        body (SecuritySeedRequest | Unset): What the caller wants seeded, and what it already
            holds

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | SecuritySeedResponse]
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
    body: SecuritySeedRequest | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | SecuritySeedResponse | None:
    """Have the leader replicate the cluster security documents

     Asks the Raft LEADER to submit server-users.jsonl, server-groups.json and server-api-tokens.json to
    the cluster, and answers with the ones that did not commit.

    Two callers need it, and both are cluster-internal. A node that has just admitted a peer reads the
    outcome here instead of running a seed of its own, so an admission is seeded once rather than from
    two nodes under two different monitors (issue #7834). A node that came back while it was still a
    Raft member - a rolling restart, a drain and reschedule, a pod whose ordinal is in the static server
    list - sends the fingerprints of the documents it holds, and is re-seeded only if they differ from
    the leader's (issue #7833); the three documents live outside the database directory, so no snapshot
    install carries them.

    Answered 409 by a node that is not the leader, naming the one it believes leads. Answered 503 with
    the failedSeeds array when the seed ran but a document did not commit, which is the same contract
    POST /api/v1/cluster/peer answers with.

    Restricted to the root user; peers satisfy this by forwarding as root with the cluster
    token.Requires RaftHAPlugin: the route is registered on every server, but answers only where high
    availability is configured.

    Args:
        x_request_id (str | Unset):
        body (SecuritySeedRequest | Unset): What the caller wants seeded, and what it already
            holds

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | SecuritySeedResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
