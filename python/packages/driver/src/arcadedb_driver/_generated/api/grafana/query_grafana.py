from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.grafana_query_request import GrafanaQueryRequest
from ...models.grafana_query_response import GrafanaQueryResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    body: GrafanaQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(arcadedb_session_id, Unset):
        headers["arcadedb-session-id"] = arcadedb_session_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/ts/{database}/grafana/query".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | GrafanaQueryResponse | None:
    if response.status_code == 200:
        response_200 = GrafanaQueryResponse.from_dict(response.json())

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

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | GrafanaQueryResponse]:
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
    body: GrafanaQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
) -> Response[ErrorResponse | GrafanaQueryResponse]:
    """Execute panel queries and return DataFrames

     Executes one query per entry in 'targets' and returns the results keyed by each target's refId, in
    the Grafana DataFrame format. A target carrying 'aggregation' produces bucketed values; a target
    without it produces raw samples, optionally projected to 'fields'. A target naming a missing type, a
    non-time-series type, or an unresolvable aggregation field gets an 'error' entry with no frames
    instead of failing the whole request. 'maxDataPoints' helps derive a bucket interval when
    'aggregation.bucketInterval' is omitted.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        body (GrafanaQueryRequest): Grafana panel query

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | GrafanaQueryResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
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
    body: GrafanaQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
) -> ErrorResponse | GrafanaQueryResponse | None:
    """Execute panel queries and return DataFrames

     Executes one query per entry in 'targets' and returns the results keyed by each target's refId, in
    the Grafana DataFrame format. A target carrying 'aggregation' produces bucketed values; a target
    without it produces raw samples, optionally projected to 'fields'. A target naming a missing type, a
    non-time-series type, or an unresolvable aggregation field gets an 'error' entry with no frames
    instead of failing the whole request. 'maxDataPoints' helps derive a bucket interval when
    'aggregation.bucketInterval' is omitted.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        body (GrafanaQueryRequest): Grafana panel query

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | GrafanaQueryResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: GrafanaQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
) -> Response[ErrorResponse | GrafanaQueryResponse]:
    """Execute panel queries and return DataFrames

     Executes one query per entry in 'targets' and returns the results keyed by each target's refId, in
    the Grafana DataFrame format. A target carrying 'aggregation' produces bucketed values; a target
    without it produces raw samples, optionally projected to 'fields'. A target naming a missing type, a
    non-time-series type, or an unresolvable aggregation field gets an 'error' entry with no frames
    instead of failing the whole request. 'maxDataPoints' helps derive a bucket interval when
    'aggregation.bucketInterval' is omitted.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        body (GrafanaQueryRequest): Grafana panel query

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | GrafanaQueryResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: GrafanaQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
) -> ErrorResponse | GrafanaQueryResponse | None:
    """Execute panel queries and return DataFrames

     Executes one query per entry in 'targets' and returns the results keyed by each target's refId, in
    the Grafana DataFrame format. A target carrying 'aggregation' produces bucketed values; a target
    without it produces raw samples, optionally projected to 'fields'. A target naming a missing type, a
    non-time-series type, or an unresolvable aggregation field gets an 'error' entry with no frames
    instead of failing the whole request. 'maxDataPoints' helps derive a bucket interval when
    'aggregation.bucketInterval' is omitted.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        body (GrafanaQueryRequest): Grafana panel query

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | GrafanaQueryResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            body=body,
            arcadedb_session_id=arcadedb_session_id,
        )
    ).parsed
