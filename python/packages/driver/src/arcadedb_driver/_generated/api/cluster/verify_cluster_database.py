from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.verify_database_cluster_response import VerifyDatabaseClusterResponse
from ...models.verify_database_local_response import VerifyDatabaseLocalResponse
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
        "url": "/api/v1/cluster/verify/{database}".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse | None:
    if response.status_code == 200:

        def _parse_response_200(data: object) -> VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_verify_database_response_type_0 = VerifyDatabaseLocalResponse.from_dict(data)

                return componentsschemas_verify_database_response_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            componentsschemas_verify_database_response_type_1 = VerifyDatabaseClusterResponse.from_dict(data)

            return componentsschemas_verify_database_response_type_1

        response_200 = _parse_response_200(response.json())

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
) -> Response[ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse]:
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
) -> Response[ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse]:
    """Checksum a database's files for comparison across peers

     Computes a per-file checksum of one database on this server. A follower returns only its own
    checksums; the leader additionally fans the same call out to every peer and reports a cluster-wide
    comparison in 'result'.Requires RaftHAPlugin: the route is registered on every server, but answers
    only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse]
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
) -> ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse | None:
    """Checksum a database's files for comparison across peers

     Computes a per-file checksum of one database on this server. A follower returns only its own
    checksums; the leader additionally fans the same call out to every peer and reports a cluster-wide
    comparison in 'result'.Requires RaftHAPlugin: the route is registered on every server, but answers
    only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse
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
) -> Response[ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse]:
    """Checksum a database's files for comparison across peers

     Computes a per-file checksum of one database on this server. A follower returns only its own
    checksums; the leader additionally fans the same call out to every peer and reports a cluster-wide
    comparison in 'result'.Requires RaftHAPlugin: the route is registered on every server, but answers
    only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse]
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
) -> ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse | None:
    """Checksum a database's files for comparison across peers

     Computes a per-file checksum of one database on this server. A follower returns only its own
    checksums; the leader additionally fans the same call out to every peer and reports a cluster-wide
    comparison in 'result'.Requires RaftHAPlugin: the route is registered on every server, but answers
    only where high availability is configured.

    Args:
        database (str):
        x_request_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | VerifyDatabaseClusterResponse | VerifyDatabaseLocalResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            x_request_id=x_request_id,
        )
    ).parsed
