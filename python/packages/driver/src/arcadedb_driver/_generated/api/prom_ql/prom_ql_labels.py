from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.prom_ql_error_response import PromQLErrorResponse
from ...models.prom_ql_labels_response import PromQLLabelsResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    arcadedb_session_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(arcadedb_session_id, Unset):
        headers["arcadedb-session-id"] = arcadedb_session_id

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/ts/{database}/prom/api/v1/labels".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse | None:
    if response.status_code == 200:
        response_200 = PromQLLabelsResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = PromQLErrorResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse]:
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
    arcadedb_session_id: str | Unset = UNSET,
) -> Response[ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse]:
    """List label names

     Lists every label name present in the database, sorted, always including '__name__'. Compatible with
    the Prometheus /api/v1/labels endpoint. Takes no filtering parameters: unlike Prometheus itself,
    this endpoint does not accept 'start', 'end', or 'match[]'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        arcadedb_session_id=arcadedb_session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
) -> ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse | None:
    """List label names

     Lists every label name present in the database, sorted, always including '__name__'. Compatible with
    the Prometheus /api/v1/labels endpoint. Takes no filtering parameters: unlike Prometheus itself,
    this endpoint does not accept 'start', 'end', or 'match[]'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        arcadedb_session_id=arcadedb_session_id,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
) -> Response[ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse]:
    """List label names

     Lists every label name present in the database, sorted, always including '__name__'. Compatible with
    the Prometheus /api/v1/labels endpoint. Takes no filtering parameters: unlike Prometheus itself,
    this endpoint does not accept 'start', 'end', or 'match[]'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        arcadedb_session_id=arcadedb_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
) -> ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse | None:
    """List label names

     Lists every label name present in the database, sorted, always including '__name__'. Compatible with
    the Prometheus /api/v1/labels endpoint. Takes no filtering parameters: unlike Prometheus itself,
    this endpoint does not accept 'start', 'end', or 'match[]'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | PromQLErrorResponse | PromQLLabelsResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            arcadedb_session_id=arcadedb_session_id,
        )
    ).parsed
