from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.full_text_search_request import FullTextSearchRequest
from ...models.full_text_search_response import FullTextSearchResponse
from ...types import Response


def _get_kwargs(
    database: str,
    *,
    body: FullTextSearchRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/vector/{database}/fulltext".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | FullTextSearchResponse | None:
    if response.status_code == 200:
        response_200 = FullTextSearchResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | FullTextSearchResponse]:
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
    body: FullTextSearchRequest,
) -> Response[ErrorResponse | FullTextSearchResponse]:
    """Full-text search over a FULL_TEXT index

     Runs a Lucene-syntax query against an ArcadeDB FULL_TEXT index and returns the matching documents
    ranked by score, highest first.

    Address the index either by 'indexName', or by 'typeName' with optional 'properties'; 'indexName'
    wins when both are supplied. Because the limit is pushed down per bucket, a hit deleted between the
    index scan and the record load is skipped rather than back-filled, so a search can legitimately
    return fewer than 'limit' results.

    Args:
        database (str):
        body (FullTextSearchRequest): Full-text search over a FULL_TEXT index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | FullTextSearchResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: FullTextSearchRequest,
) -> ErrorResponse | FullTextSearchResponse | None:
    """Full-text search over a FULL_TEXT index

     Runs a Lucene-syntax query against an ArcadeDB FULL_TEXT index and returns the matching documents
    ranked by score, highest first.

    Address the index either by 'indexName', or by 'typeName' with optional 'properties'; 'indexName'
    wins when both are supplied. Because the limit is pushed down per bucket, a hit deleted between the
    index scan and the record load is skipped rather than back-filled, so a search can legitimately
    return fewer than 'limit' results.

    Args:
        database (str):
        body (FullTextSearchRequest): Full-text search over a FULL_TEXT index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | FullTextSearchResponse
    """

    return sync_detailed(
        database=database,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: FullTextSearchRequest,
) -> Response[ErrorResponse | FullTextSearchResponse]:
    """Full-text search over a FULL_TEXT index

     Runs a Lucene-syntax query against an ArcadeDB FULL_TEXT index and returns the matching documents
    ranked by score, highest first.

    Address the index either by 'indexName', or by 'typeName' with optional 'properties'; 'indexName'
    wins when both are supplied. Because the limit is pushed down per bucket, a hit deleted between the
    index scan and the record load is skipped rather than back-filled, so a search can legitimately
    return fewer than 'limit' results.

    Args:
        database (str):
        body (FullTextSearchRequest): Full-text search over a FULL_TEXT index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | FullTextSearchResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    *,
    client: AuthenticatedClient | Client,
    body: FullTextSearchRequest,
) -> ErrorResponse | FullTextSearchResponse | None:
    """Full-text search over a FULL_TEXT index

     Runs a Lucene-syntax query against an ArcadeDB FULL_TEXT index and returns the matching documents
    ranked by score, highest first.

    Address the index either by 'indexName', or by 'typeName' with optional 'properties'; 'indexName'
    wins when both are supplied. Because the limit is pushed down per bucket, a hit deleted between the
    index scan and the record load is skipped rather than back-filled, so a search can legitimately
    return fewer than 'limit' results.

    Args:
        database (str):
        body (FullTextSearchRequest): Full-text search over a FULL_TEXT index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | FullTextSearchResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            body=body,
        )
    ).parsed
