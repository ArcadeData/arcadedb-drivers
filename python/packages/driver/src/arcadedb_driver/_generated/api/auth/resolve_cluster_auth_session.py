from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.cluster_auth_session_request import ClusterAuthSessionRequest
from ...models.cluster_auth_session_response import ClusterAuthSessionResponse
from ...models.error_response import ErrorResponse
from ...types import Response


def _get_kwargs(
    *,
    body: ClusterAuthSessionRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/cluster/auth-session",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ClusterAuthSessionResponse | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = ClusterAuthSessionResponse.from_dict(response.json())

        return response_200

    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | ClusterAuthSessionResponse | ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ClusterAuthSessionRequest,
) -> Response[Any | ClusterAuthSessionResponse | ErrorResponse]:
    """Confirm or revoke an authentication session on the node that issued it

     Cluster-internal. A session token is held by the node that answered /api/v1/login and names that
    node ('AU-<server name>-<uuid>'). A peer that receives the token asks the issuer through this route
    whether the session is still valid ('validate', which also counts as activity on the issuer), and a
    logout tells every peer to drop its copy ('revoke'). Peers authenticate with the cluster token; a
    request that carries user credentials instead is refused with 403 (issue #7424).

    Args:
        body (ClusterAuthSessionRequest): A session token and the action to apply to it

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ClusterAuthSessionResponse | ErrorResponse]
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
    body: ClusterAuthSessionRequest,
) -> Any | ClusterAuthSessionResponse | ErrorResponse | None:
    """Confirm or revoke an authentication session on the node that issued it

     Cluster-internal. A session token is held by the node that answered /api/v1/login and names that
    node ('AU-<server name>-<uuid>'). A peer that receives the token asks the issuer through this route
    whether the session is still valid ('validate', which also counts as activity on the issuer), and a
    logout tells every peer to drop its copy ('revoke'). Peers authenticate with the cluster token; a
    request that carries user credentials instead is refused with 403 (issue #7424).

    Args:
        body (ClusterAuthSessionRequest): A session token and the action to apply to it

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ClusterAuthSessionResponse | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ClusterAuthSessionRequest,
) -> Response[Any | ClusterAuthSessionResponse | ErrorResponse]:
    """Confirm or revoke an authentication session on the node that issued it

     Cluster-internal. A session token is held by the node that answered /api/v1/login and names that
    node ('AU-<server name>-<uuid>'). A peer that receives the token asks the issuer through this route
    whether the session is still valid ('validate', which also counts as activity on the issuer), and a
    logout tells every peer to drop its copy ('revoke'). Peers authenticate with the cluster token; a
    request that carries user credentials instead is refused with 403 (issue #7424).

    Args:
        body (ClusterAuthSessionRequest): A session token and the action to apply to it

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ClusterAuthSessionResponse | ErrorResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ClusterAuthSessionRequest,
) -> Any | ClusterAuthSessionResponse | ErrorResponse | None:
    """Confirm or revoke an authentication session on the node that issued it

     Cluster-internal. A session token is held by the node that answered /api/v1/login and names that
    node ('AU-<server name>-<uuid>'). A peer that receives the token asks the issuer through this route
    whether the session is still valid ('validate', which also counts as activity on the issuer), and a
    logout tells every peer to drop its copy ('revoke'). Peers authenticate with the cluster token; a
    request that carries user credentials instead is refused with 403 (issue #7424).

    Args:
        body (ClusterAuthSessionRequest): A session token and the action to apply to it

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ClusterAuthSessionResponse | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
