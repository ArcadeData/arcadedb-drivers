from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.execute_query_get_accept import ExecuteQueryGetAccept
from ...models.execute_query_get_language import ExecuteQueryGetLanguage
from ...models.query_response import QueryResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    database: str,
    language: ExecuteQueryGetLanguage,
    command: str,
    *,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteQueryGetAccept | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(arcadedb_session_id, Unset):
        headers["arcadedb-session-id"] = arcadedb_session_id

    if not isinstance(accept, Unset):
        headers["Accept"] = str(accept)

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/query/{database}/{language}/{command}".format(
            database=quote(str(database), safe=""),
            language=quote(str(language), safe=""),
            command=quote(str(command), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | QueryResponse | None:
    if response.status_code == 200:
        response_200 = QueryResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = ErrorResponse.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 404:
        response_404 = ErrorResponse.from_dict(response.json())

        return response_404

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
) -> Response[ErrorResponse | QueryResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    database: str,
    language: ExecuteQueryGetLanguage,
    command: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteQueryGetAccept | Unset = UNSET,
) -> Response[ErrorResponse | QueryResponse]:
    """Execute query via GET

     Executes a query using GET method with parameters in URL

    Args:
        database (str):
        language (ExecuteQueryGetLanguage):
        command (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteQueryGetAccept | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        language=language,
        command=command,
        arcadedb_session_id=arcadedb_session_id,
        accept=accept,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    database: str,
    language: ExecuteQueryGetLanguage,
    command: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteQueryGetAccept | Unset = UNSET,
) -> ErrorResponse | QueryResponse | None:
    """Execute query via GET

     Executes a query using GET method with parameters in URL

    Args:
        database (str):
        language (ExecuteQueryGetLanguage):
        command (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteQueryGetAccept | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | QueryResponse
    """

    return sync_detailed(
        database=database,
        language=language,
        command=command,
        client=client,
        arcadedb_session_id=arcadedb_session_id,
        accept=accept,
    ).parsed


async def asyncio_detailed(
    database: str,
    language: ExecuteQueryGetLanguage,
    command: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteQueryGetAccept | Unset = UNSET,
) -> Response[ErrorResponse | QueryResponse]:
    """Execute query via GET

     Executes a query using GET method with parameters in URL

    Args:
        database (str):
        language (ExecuteQueryGetLanguage):
        command (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteQueryGetAccept | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | QueryResponse]
    """

    kwargs = _get_kwargs(
        database=database,
        language=language,
        command=command,
        arcadedb_session_id=arcadedb_session_id,
        accept=accept,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    database: str,
    language: ExecuteQueryGetLanguage,
    command: str,
    *,
    client: AuthenticatedClient | Client,
    arcadedb_session_id: str | Unset = UNSET,
    accept: ExecuteQueryGetAccept | Unset = UNSET,
) -> ErrorResponse | QueryResponse | None:
    """Execute query via GET

     Executes a query using GET method with parameters in URL

    Args:
        database (str):
        language (ExecuteQueryGetLanguage):
        command (str):
        arcadedb_session_id (str | Unset):
        accept (ExecuteQueryGetAccept | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | QueryResponse
    """

    return (
        await asyncio_detailed(
            database=database,
            language=language,
            command=command,
            client=client,
            arcadedb_session_id=arcadedb_session_id,
            accept=accept,
        )
    ).parsed
