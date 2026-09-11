from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.time_series_latest_response import TimeSeriesLatestResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    *,
    type_: str,
    tag: list[str] | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["type"] = type_

    json_tag: list[str] | Unset = UNSET
    if not isinstance(tag, Unset):
        json_tag = tag

    params["tag"] = json_tag

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/ts/{database}/latest".format(
            database=quote(str(database), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | TimeSeriesLatestResponse | None:
    if response.status_code == 200:
        response_200 = TimeSeriesLatestResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | TimeSeriesLatestResponse]:
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
    type_: str,
    tag: list[str] | Unset = UNSET,
) -> Response[ErrorResponse | TimeSeriesLatestResponse]:
    """Read the most recent sample of a series

     Returns the most recent sample of a time-series type, optionally narrowed to one series by tag.
    Repeat 'tag' once per tag column to name a single series on a type that carries several. 'latest' is
    null when the type or the selected series holds no sample.

    Args:
        database (str):
        type_ (str):
        tag (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | TimeSeriesLatestResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        type_=type_,
        tag=tag,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    type_: str,
    tag: list[str] | Unset = UNSET,
) -> ErrorResponse | TimeSeriesLatestResponse | None:
    """Read the most recent sample of a series

     Returns the most recent sample of a time-series type, optionally narrowed to one series by tag.
    Repeat 'tag' once per tag column to name a single series on a type that carries several. 'latest' is
    null when the type or the selected series holds no sample.

    Args:
        database (str):
        type_ (str):
        tag (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | TimeSeriesLatestResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        type_=type_,
        tag=tag,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    type_: str,
    tag: list[str] | Unset = UNSET,
) -> Response[ErrorResponse | TimeSeriesLatestResponse]:
    """Read the most recent sample of a series

     Returns the most recent sample of a time-series type, optionally narrowed to one series by tag.
    Repeat 'tag' once per tag column to name a single series on a type that carries several. 'latest' is
    null when the type or the selected series holds no sample.

    Args:
        database (str):
        type_ (str):
        tag (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | TimeSeriesLatestResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        type_=type_,
        tag=tag,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    type_: str,
    tag: list[str] | Unset = UNSET,
) -> ErrorResponse | TimeSeriesLatestResponse | None:
    """Read the most recent sample of a series

     Returns the most recent sample of a time-series type, optionally narrowed to one series by tag.
    Repeat 'tag' once per tag column to name a single series on a type that carries several. 'latest' is
    null when the type or the selected series holds no sample.

    Args:
        database (str):
        type_ (str):
        tag (list[str] | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | TimeSeriesLatestResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            type_=type_,
            tag=tag,
        )
    ).parsed
