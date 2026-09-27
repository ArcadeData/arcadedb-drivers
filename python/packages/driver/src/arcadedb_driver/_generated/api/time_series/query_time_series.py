from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.time_series_aggregated_response import TimeSeriesAggregatedResponse
from ...models.time_series_query_request import TimeSeriesQueryRequest
from ...models.time_series_raw_response import TimeSeriesRawResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    body: TimeSeriesQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(arcadedb_session_id, Unset):
        headers["arcadedb-session-id"] = arcadedb_session_id

    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/ts/{database}/query".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse | None:
    if response.status_code == 200:

        def _parse_response_200(data: object) -> TimeSeriesAggregatedResponse | TimeSeriesRawResponse:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                response_200_type_0 = TimeSeriesRawResponse.from_dict(data)

                return response_200_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, dict):
                raise TypeError()
            response_200_type_1 = TimeSeriesAggregatedResponse.from_dict(data)

            return response_200_type_1

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

    if response.status_code == 413:
        response_413 = ErrorResponse.from_dict(response.json())

        return response_413

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse]:
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
    body: TimeSeriesQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse]:
    """Query samples, optionally aggregated into buckets

     Reads samples from a time-series type over a timestamp range, optionally filtered by tag and
    projected to a subset of fields.

    The response shape depends on the request: without 'aggregation' it carries raw rows under 'rows';
    with 'aggregation' it carries fixed-interval buckets under 'buckets' and names the computed
    aggregations under 'aggregations'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        x_request_id (str | Unset):
        body (TimeSeriesQueryRequest): Time-series query definition

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
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
    body: TimeSeriesQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse | None:
    """Query samples, optionally aggregated into buckets

     Reads samples from a time-series type over a timestamp range, optionally filtered by tag and
    projected to a subset of fields.

    The response shape depends on the request: without 'aggregation' it carries raw rows under 'rows';
    with 'aggregation' it carries fixed-interval buckets under 'buckets' and names the computed
    aggregations under 'aggregations'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        x_request_id (str | Unset):
        body (TimeSeriesQueryRequest): Time-series query definition

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: TimeSeriesQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse]:
    """Query samples, optionally aggregated into buckets

     Reads samples from a time-series type over a timestamp range, optionally filtered by tag and
    projected to a subset of fields.

    The response shape depends on the request: without 'aggregation' it carries raw rows under 'rows';
    with 'aggregation' it carries fixed-interval buckets under 'buckets' and names the computed
    aggregations under 'aggregations'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        x_request_id (str | Unset):
        body (TimeSeriesQueryRequest): Time-series query definition

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
        arcadedb_session_id=arcadedb_session_id,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: TimeSeriesQueryRequest,
    arcadedb_session_id: str | Unset = UNSET,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse | None:
    """Query samples, optionally aggregated into buckets

     Reads samples from a time-series type over a timestamp range, optionally filtered by tag and
    projected to a subset of fields.

    The response shape depends on the request: without 'aggregation' it carries raw rows under 'rows';
    with 'aggregation' it carries fixed-interval buckets under 'buckets' and names the computed
    aggregations under 'aggregations'.

    Args:
        database (str):
        arcadedb_session_id (str | Unset):
        x_request_id (str | Unset):
        body (TimeSeriesQueryRequest): Time-series query definition

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | TimeSeriesAggregatedResponse | TimeSeriesRawResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            body=body,
            arcadedb_session_id=arcadedb_session_id,
            x_request_id=x_request_id,
        )
    ).parsed
