from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.prom_ql_error_response import PromQLErrorResponse
from ...models.prom_ql_series_response import PromQLSeriesResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    match: list[str],
    start: str | Unset = UNSET,
    end: str | Unset = UNSET,
    arcadedb_session_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(arcadedb_session_id, Unset):
        headers["arcadedb-session-id"] = arcadedb_session_id

    params: dict[str, Any] = {}

    json_match = match

    params["match[]"] = json_match

    params["start"] = start

    params["end"] = end

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/ts/{database}/prom/api/v1/series".format(
            database=quote(str(database), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse | None:
    if response.status_code == 200:
        response_200 = PromQLSeriesResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse]:
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
    match: list[str],
    start: str | Unset = UNSET,
    end: str | Unset = UNSET,
    arcadedb_session_id: str | Unset = UNSET,
) -> Response[ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse]:
    """Find series matching selectors

     Returns the label sets of the series matching the given selectors. Compatible with the Prometheus
    /api/v1/series endpoint. Each returned object is a label map including the '__name__' label. A
    selector that fails to parse is skipped rather than rejected, so a mix of valid and malformed
    'match[]' values still returns the matches from the valid ones.

    Args:
        database (str):
        match (list[str]):
        start (str | Unset):
        end (str | Unset):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        match=match,
        start=start,
        end=end,
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
    match: list[str],
    start: str | Unset = UNSET,
    end: str | Unset = UNSET,
    arcadedb_session_id: str | Unset = UNSET,
) -> ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse | None:
    """Find series matching selectors

     Returns the label sets of the series matching the given selectors. Compatible with the Prometheus
    /api/v1/series endpoint. Each returned object is a label map including the '__name__' label. A
    selector that fails to parse is skipped rather than rejected, so a mix of valid and malformed
    'match[]' values still returns the matches from the valid ones.

    Args:
        database (str):
        match (list[str]):
        start (str | Unset):
        end (str | Unset):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        match=match,
        start=start,
        end=end,
        arcadedb_session_id=arcadedb_session_id,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    match: list[str],
    start: str | Unset = UNSET,
    end: str | Unset = UNSET,
    arcadedb_session_id: str | Unset = UNSET,
) -> Response[ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse]:
    """Find series matching selectors

     Returns the label sets of the series matching the given selectors. Compatible with the Prometheus
    /api/v1/series endpoint. Each returned object is a label map including the '__name__' label. A
    selector that fails to parse is skipped rather than rejected, so a mix of valid and malformed
    'match[]' values still returns the matches from the valid ones.

    Args:
        database (str):
        match (list[str]):
        start (str | Unset):
        end (str | Unset):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        match=match,
        start=start,
        end=end,
        arcadedb_session_id=arcadedb_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    match: list[str],
    start: str | Unset = UNSET,
    end: str | Unset = UNSET,
    arcadedb_session_id: str | Unset = UNSET,
) -> ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse | None:
    """Find series matching selectors

     Returns the label sets of the series matching the given selectors. Compatible with the Prometheus
    /api/v1/series endpoint. Each returned object is a label map including the '__name__' label. A
    selector that fails to parse is skipped rather than rejected, so a mix of valid and malformed
    'match[]' values still returns the matches from the valid ones.

    Args:
        database (str):
        match (list[str]):
        start (str | Unset):
        end (str | Unset):
        arcadedb_session_id (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | PromQLErrorResponse | PromQLSeriesResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            match=match,
            start=start,
            end=end,
            arcadedb_session_id=arcadedb_session_id,
        )
    ).parsed
