from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.vector_search_request import VectorSearchRequest
from ...models.vector_search_response import VectorSearchResponse
from ...types import Response


def _get_kwargs(
    database: str,
    *,
    body: VectorSearchRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/vector/{database}/search".format(
            database=quote(str(database), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | VectorSearchResponse | None:
    if response.status_code == 200:
        response_200 = VectorSearchResponse.from_dict(response.json())

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
) -> Response[ErrorResponse | VectorSearchResponse]:
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
    body: VectorSearchRequest,
) -> Response[ErrorResponse | VectorSearchResponse]:
    """kNN search over a vector index

     Returns the nearest neighbors of a pre-computed query vector in a dense LSM_VECTOR or sparse
    LSM_SPARSE_VECTOR index. ArcadeDB does not generate embeddings: the caller supplies the vector.

    Dense results expose a 'distance' (lower is better); sparse results expose a 'score' (higher is
    better), and 'scoring' names which of the two the response carries. A filtered search inspects a
    bounded candidate window whose size is reported as 'candidateLimit', so 'truncated' means the window
    was filled and more matches may exist - raise 'k' to see them.

    Args:
        database (str):
        body (VectorSearchRequest): kNN search over a dense or sparse vector index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | VectorSearchResponse]
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
    body: VectorSearchRequest,
) -> ErrorResponse | VectorSearchResponse | None:
    """kNN search over a vector index

     Returns the nearest neighbors of a pre-computed query vector in a dense LSM_VECTOR or sparse
    LSM_SPARSE_VECTOR index. ArcadeDB does not generate embeddings: the caller supplies the vector.

    Dense results expose a 'distance' (lower is better); sparse results expose a 'score' (higher is
    better), and 'scoring' names which of the two the response carries. A filtered search inspects a
    bounded candidate window whose size is reported as 'candidateLimit', so 'truncated' means the window
    was filled and more matches may exist - raise 'k' to see them.

    Args:
        database (str):
        body (VectorSearchRequest): kNN search over a dense or sparse vector index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | VectorSearchResponse
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
    body: VectorSearchRequest,
) -> Response[ErrorResponse | VectorSearchResponse]:
    """kNN search over a vector index

     Returns the nearest neighbors of a pre-computed query vector in a dense LSM_VECTOR or sparse
    LSM_SPARSE_VECTOR index. ArcadeDB does not generate embeddings: the caller supplies the vector.

    Dense results expose a 'distance' (lower is better); sparse results expose a 'score' (higher is
    better), and 'scoring' names which of the two the response carries. A filtered search inspects a
    bounded candidate window whose size is reported as 'candidateLimit', so 'truncated' means the window
    was filled and more matches may exist - raise 'k' to see them.

    Args:
        database (str):
        body (VectorSearchRequest): kNN search over a dense or sparse vector index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | VectorSearchResponse]
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
    body: VectorSearchRequest,
) -> ErrorResponse | VectorSearchResponse | None:
    """kNN search over a vector index

     Returns the nearest neighbors of a pre-computed query vector in a dense LSM_VECTOR or sparse
    LSM_SPARSE_VECTOR index. ArcadeDB does not generate embeddings: the caller supplies the vector.

    Dense results expose a 'distance' (lower is better); sparse results expose a 'score' (higher is
    better), and 'scoring' names which of the two the response carries. A filtered search inspects a
    bounded candidate window whose size is reported as 'candidateLimit', so 'truncated' means the window
    was filled and more matches may exist - raise 'k' to see them.

    Args:
        database (str):
        body (VectorSearchRequest): kNN search over a dense or sparse vector index

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | VectorSearchResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            client=client,
            body=body,
        )
    ).parsed
