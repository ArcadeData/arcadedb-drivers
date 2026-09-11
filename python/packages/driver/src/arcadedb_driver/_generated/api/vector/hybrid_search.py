from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.hybrid_search_request import HybridSearchRequest
from ...models.hybrid_search_response import HybridSearchResponse
from ...types import Response


def _get_kwargs(
    database: str,
    *,
    body: HybridSearchRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/vector/{database}/hybrid".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | HybridSearchResponse | None:
    if response.status_code == 200:
        response_200 = HybridSearchResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | HybridSearchResponse]:
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
    body: HybridSearchRequest,
) -> Response[ErrorResponse | HybridSearchResponse]:
    """Fused vector, full-text and graph-expansion search

     Fuses a vector retrieval leg, an optional full-text retrieval leg and an optional depth-limited
    graph expansion leg into one ranked list, using the engine's own vector.fuse rather than a re-
    implementation.

    Fusion needs at least two sources. A request naming only the vector leg reports 'fused': false and
    returns that leg's native distance or score rather than a fabricated fused one. The expansion leg is
    ranked by traversal order and carries no score, so it can only be fused with the RRF strategy.

    Args:
        database (str):
        body (HybridSearchRequest): Fused vector, full-text and graph-expansion search

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | HybridSearchResponse]
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
    body: HybridSearchRequest,
) -> ErrorResponse | HybridSearchResponse | None:
    """Fused vector, full-text and graph-expansion search

     Fuses a vector retrieval leg, an optional full-text retrieval leg and an optional depth-limited
    graph expansion leg into one ranked list, using the engine's own vector.fuse rather than a re-
    implementation.

    Fusion needs at least two sources. A request naming only the vector leg reports 'fused': false and
    returns that leg's native distance or score rather than a fabricated fused one. The expansion leg is
    ranked by traversal order and carries no score, so it can only be fused with the RRF strategy.

    Args:
        database (str):
        body (HybridSearchRequest): Fused vector, full-text and graph-expansion search

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | HybridSearchResponse
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
    body: HybridSearchRequest,
) -> Response[ErrorResponse | HybridSearchResponse]:
    """Fused vector, full-text and graph-expansion search

     Fuses a vector retrieval leg, an optional full-text retrieval leg and an optional depth-limited
    graph expansion leg into one ranked list, using the engine's own vector.fuse rather than a re-
    implementation.

    Fusion needs at least two sources. A request naming only the vector leg reports 'fused': false and
    returns that leg's native distance or score rather than a fabricated fused one. The expansion leg is
    ranked by traversal order and carries no score, so it can only be fused with the RRF strategy.

    Args:
        database (str):
        body (HybridSearchRequest): Fused vector, full-text and graph-expansion search

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | HybridSearchResponse]
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
    body: HybridSearchRequest,
) -> ErrorResponse | HybridSearchResponse | None:
    """Fused vector, full-text and graph-expansion search

     Fuses a vector retrieval leg, an optional full-text retrieval leg and an optional depth-limited
    graph expansion leg into one ranked list, using the engine's own vector.fuse rather than a re-
    implementation.

    Fusion needs at least two sources. A request naming only the vector leg reports 'fused': false and
    returns that leg's native distance or score rather than a fabricated fused one. The expansion leg is
    ranked by traversal order and carries no score, so it can only be fused with the RRF strategy.

    Args:
        database (str):
        body (HybridSearchRequest): Fused vector, full-text and graph-expansion search

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | HybridSearchResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            body=body,
        )
    ).parsed
