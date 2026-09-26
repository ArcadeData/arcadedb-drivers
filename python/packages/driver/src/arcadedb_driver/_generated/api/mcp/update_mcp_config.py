from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.mcp_config import McpConfig
from ...models.mcp_config_update import McpConfigUpdate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: McpConfigUpdate,
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/mcp/config",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ErrorResponse | McpConfig | None:
    if response.status_code == 200:
        response_200 = McpConfig.from_dict(response.json())

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

    if response.status_code == 405:
        response_405 = ErrorResponse.from_dict(response.json())

        return response_405

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
) -> Response[ErrorResponse | McpConfig]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: McpConfigUpdate,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | McpConfig]:
    """Update the MCP server configuration

     Applies a partial configuration update: send only the fields to change. The update is all-or-
    nothing: every field is parsed and validated before the first one is assigned, so a payload rejected
    on any field leaves the configuration exactly as it was. Restricted to the root user.

    Answers with the full configuration as it stands after the update. Requires MCPPlugin: present in
    every standard distribution, absent from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (McpConfigUpdate): A partial MCP server configuration. Send only the fields to
            change; an omitted one keeps its current value, so nothing here is required. The update is
            all-or-nothing: every field is parsed and validated before the first one is assigned.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | McpConfig]
    """

    kwargs = _get_kwargs(
        body=body,
        x_request_id=x_request_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: McpConfigUpdate,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | McpConfig | None:
    """Update the MCP server configuration

     Applies a partial configuration update: send only the fields to change. The update is all-or-
    nothing: every field is parsed and validated before the first one is assigned, so a payload rejected
    on any field leaves the configuration exactly as it was. Restricted to the root user.

    Answers with the full configuration as it stands after the update. Requires MCPPlugin: present in
    every standard distribution, absent from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (McpConfigUpdate): A partial MCP server configuration. Send only the fields to
            change; an omitted one keeps its current value, so nothing here is required. The update is
            all-or-nothing: every field is parsed and validated before the first one is assigned.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | McpConfig
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: McpConfigUpdate,
    x_request_id: str | Unset = UNSET,
) -> Response[ErrorResponse | McpConfig]:
    """Update the MCP server configuration

     Applies a partial configuration update: send only the fields to change. The update is all-or-
    nothing: every field is parsed and validated before the first one is assigned, so a payload rejected
    on any field leaves the configuration exactly as it was. Restricted to the root user.

    Answers with the full configuration as it stands after the update. Requires MCPPlugin: present in
    every standard distribution, absent from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (McpConfigUpdate): A partial MCP server configuration. Send only the fields to
            change; an omitted one keeps its current value, so nothing here is required. The update is
            all-or-nothing: every field is parsed and validated before the first one is assigned.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ErrorResponse | McpConfig]
    """

    kwargs = _get_kwargs(
        body=body,
        x_request_id=x_request_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: McpConfigUpdate,
    x_request_id: str | Unset = UNSET,
) -> ErrorResponse | McpConfig | None:
    """Update the MCP server configuration

     Applies a partial configuration update: send only the fields to change. The update is all-or-
    nothing: every field is parsed and validated before the first one is assigned, so a payload rejected
    on any field leaves the configuration exactly as it was. Restricted to the root user.

    Answers with the full configuration as it stands after the update. Requires MCPPlugin: present in
    every standard distribution, absent from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (McpConfigUpdate): A partial MCP server configuration. Send only the fields to
            change; an omitted one keeps its current value, so nothing here is required. The update is
            all-or-nothing: every field is parsed and validated before the first one is assigned.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ErrorResponse | McpConfig
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
