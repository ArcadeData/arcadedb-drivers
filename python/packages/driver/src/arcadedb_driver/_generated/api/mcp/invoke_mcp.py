from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.error_response import ErrorResponse
from ...models.json_rpc_message_type_0 import JsonRpcMessageType0
from ...models.json_rpc_message_type_1_item import JsonRpcMessageType1Item
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: JsonRpcMessageType0 | list[JsonRpcMessageType1Item],
    x_request_id: str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_request_id, Unset):
        headers["X-Request-Id"] = x_request_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/mcp",
    }

    if isinstance(body, JsonRpcMessageType0):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = []
        for componentsschemas_json_rpc_message_type_1_item_data in body:
            componentsschemas_json_rpc_message_type_1_item = (
                componentsschemas_json_rpc_message_type_1_item_data.to_dict()
            )
            _kwargs["json"].append(componentsschemas_json_rpc_message_type_1_item)

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item] | None:
    if response.status_code == 200:

        def _parse_response_200(data: object) -> JsonRpcMessageType0 | list[JsonRpcMessageType1Item]:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_json_rpc_message_type_0 = JsonRpcMessageType0.from_dict(data)

                return componentsschemas_json_rpc_message_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            componentsschemas_json_rpc_message_type_1 = []
            _componentsschemas_json_rpc_message_type_1 = data
            for componentsschemas_json_rpc_message_type_1_item_data in _componentsschemas_json_rpc_message_type_1:
                componentsschemas_json_rpc_message_type_1_item = JsonRpcMessageType1Item.from_dict(
                    componentsschemas_json_rpc_message_type_1_item_data
                )

                componentsschemas_json_rpc_message_type_1.append(componentsschemas_json_rpc_message_type_1_item)

            return componentsschemas_json_rpc_message_type_1

        response_200 = _parse_response_200(response.json())

        return response_200

    if response.status_code == 202:
        response_202 = cast(Any, None)
        return response_202

    if response.status_code == 401:
        response_401 = ErrorResponse.from_dict(response.json())

        return response_401

    if response.status_code == 403:

        def _parse_response_403(data: object) -> JsonRpcMessageType0 | list[JsonRpcMessageType1Item]:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_json_rpc_message_type_0 = JsonRpcMessageType0.from_dict(data)

                return componentsschemas_json_rpc_message_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            componentsschemas_json_rpc_message_type_1 = []
            _componentsschemas_json_rpc_message_type_1 = data
            for componentsschemas_json_rpc_message_type_1_item_data in _componentsschemas_json_rpc_message_type_1:
                componentsschemas_json_rpc_message_type_1_item = JsonRpcMessageType1Item.from_dict(
                    componentsschemas_json_rpc_message_type_1_item_data
                )

                componentsschemas_json_rpc_message_type_1.append(componentsschemas_json_rpc_message_type_1_item)

            return componentsschemas_json_rpc_message_type_1

        response_403 = _parse_response_403(response.json())

        return response_403

    if response.status_code == 405:

        def _parse_response_405(data: object) -> JsonRpcMessageType0 | list[JsonRpcMessageType1Item]:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_json_rpc_message_type_0 = JsonRpcMessageType0.from_dict(data)

                return componentsschemas_json_rpc_message_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            componentsschemas_json_rpc_message_type_1 = []
            _componentsschemas_json_rpc_message_type_1 = data
            for componentsschemas_json_rpc_message_type_1_item_data in _componentsschemas_json_rpc_message_type_1:
                componentsschemas_json_rpc_message_type_1_item = JsonRpcMessageType1Item.from_dict(
                    componentsschemas_json_rpc_message_type_1_item_data
                )

                componentsschemas_json_rpc_message_type_1.append(componentsschemas_json_rpc_message_type_1_item)

            return componentsschemas_json_rpc_message_type_1

        response_405 = _parse_response_405(response.json())

        return response_405

    if response.status_code == 409:
        response_409 = ErrorResponse.from_dict(response.json())

        return response_409

    if response.status_code == 500:
        response_500 = ErrorResponse.from_dict(response.json())

        return response_500

    if response.status_code == 503:

        def _parse_response_503(data: object) -> JsonRpcMessageType0 | list[JsonRpcMessageType1Item]:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                componentsschemas_json_rpc_message_type_0 = JsonRpcMessageType0.from_dict(data)

                return componentsschemas_json_rpc_message_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            if not isinstance(data, list):
                raise TypeError()
            componentsschemas_json_rpc_message_type_1 = []
            _componentsschemas_json_rpc_message_type_1 = data
            for componentsschemas_json_rpc_message_type_1_item_data in _componentsschemas_json_rpc_message_type_1:
                componentsschemas_json_rpc_message_type_1_item = JsonRpcMessageType1Item.from_dict(
                    componentsschemas_json_rpc_message_type_1_item_data
                )

                componentsschemas_json_rpc_message_type_1.append(componentsschemas_json_rpc_message_type_1_item)

            return componentsschemas_json_rpc_message_type_1

        response_503 = _parse_response_503(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: JsonRpcMessageType0 | list[JsonRpcMessageType1Item],
    x_request_id: str | Unset = UNSET,
) -> Response[Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]]:
    """Exchange a JSON-RPC message with the MCP server

     Accepts one JSON-RPC 2.0 request, notification, or response, or a batch of them as a top-level
    array, and answers with the corresponding response. The method set and the parameter and result
    shapes for each method are defined by the Model Context Protocol specification, not by this API, so
    request and response bodies are not enumerated here.

    The route is always registered; when the MCP server is disabled the request is refused at request
    time with 503, which is what makes runtime toggling possible without a restart. A request carrying
    only notifications and/or responses receives 202 with no body, because JSON-RPC forbids replying to
    those. Every other outcome, including a JSON-RPC-level error such as an unknown method or a
    malformed request body, is reported inside a 200 response: JSON-RPC layers its own error reporting
    over the HTTP transport, so a non-200 status is reserved for transport-level failures such as
    missing credentials, a disallowed browser Origin, an unauthorized user, an unsupported HTTP method,
    or the server being disabled. Requires MCPPlugin: present in every standard distribution, absent
    from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (JsonRpcMessageType0 | list[JsonRpcMessageType1Item]): One JSON-RPC 2.0 message, or a
            batch of them as a top-level array. A batch request is answered by a batch of responses.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]]
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
    body: JsonRpcMessageType0 | list[JsonRpcMessageType1Item],
    x_request_id: str | Unset = UNSET,
) -> Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item] | None:
    """Exchange a JSON-RPC message with the MCP server

     Accepts one JSON-RPC 2.0 request, notification, or response, or a batch of them as a top-level
    array, and answers with the corresponding response. The method set and the parameter and result
    shapes for each method are defined by the Model Context Protocol specification, not by this API, so
    request and response bodies are not enumerated here.

    The route is always registered; when the MCP server is disabled the request is refused at request
    time with 503, which is what makes runtime toggling possible without a restart. A request carrying
    only notifications and/or responses receives 202 with no body, because JSON-RPC forbids replying to
    those. Every other outcome, including a JSON-RPC-level error such as an unknown method or a
    malformed request body, is reported inside a 200 response: JSON-RPC layers its own error reporting
    over the HTTP transport, so a non-200 status is reserved for transport-level failures such as
    missing credentials, a disallowed browser Origin, an unauthorized user, an unsupported HTTP method,
    or the server being disabled. Requires MCPPlugin: present in every standard distribution, absent
    from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (JsonRpcMessageType0 | list[JsonRpcMessageType1Item]): One JSON-RPC 2.0 message, or a
            batch of them as a top-level array. A batch request is answered by a batch of responses.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]
    """

    return sync_detailed(
        client=client,
        body=body,
        x_request_id=x_request_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: JsonRpcMessageType0 | list[JsonRpcMessageType1Item],
    x_request_id: str | Unset = UNSET,
) -> Response[Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]]:
    """Exchange a JSON-RPC message with the MCP server

     Accepts one JSON-RPC 2.0 request, notification, or response, or a batch of them as a top-level
    array, and answers with the corresponding response. The method set and the parameter and result
    shapes for each method are defined by the Model Context Protocol specification, not by this API, so
    request and response bodies are not enumerated here.

    The route is always registered; when the MCP server is disabled the request is refused at request
    time with 503, which is what makes runtime toggling possible without a restart. A request carrying
    only notifications and/or responses receives 202 with no body, because JSON-RPC forbids replying to
    those. Every other outcome, including a JSON-RPC-level error such as an unknown method or a
    malformed request body, is reported inside a 200 response: JSON-RPC layers its own error reporting
    over the HTTP transport, so a non-200 status is reserved for transport-level failures such as
    missing credentials, a disallowed browser Origin, an unauthorized user, an unsupported HTTP method,
    or the server being disabled. Requires MCPPlugin: present in every standard distribution, absent
    from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (JsonRpcMessageType0 | list[JsonRpcMessageType1Item]): One JSON-RPC 2.0 message, or a
            batch of them as a top-level array. A batch request is answered by a batch of responses.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]]
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
    body: JsonRpcMessageType0 | list[JsonRpcMessageType1Item],
    x_request_id: str | Unset = UNSET,
) -> Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item] | None:
    """Exchange a JSON-RPC message with the MCP server

     Accepts one JSON-RPC 2.0 request, notification, or response, or a batch of them as a top-level
    array, and answers with the corresponding response. The method set and the parameter and result
    shapes for each method are defined by the Model Context Protocol specification, not by this API, so
    request and response bodies are not enumerated here.

    The route is always registered; when the MCP server is disabled the request is refused at request
    time with 503, which is what makes runtime toggling possible without a restart. A request carrying
    only notifications and/or responses receives 202 with no body, because JSON-RPC forbids replying to
    those. Every other outcome, including a JSON-RPC-level error such as an unknown method or a
    malformed request body, is reported inside a 200 response: JSON-RPC layers its own error reporting
    over the HTTP transport, so a non-200 status is reserved for transport-level failures such as
    missing credentials, a disallowed browser Origin, an unauthorized user, an unsupported HTTP method,
    or the server being disabled. Requires MCPPlugin: present in every standard distribution, absent
    from a custom build that excludes the MCP module.

    Args:
        x_request_id (str | Unset):
        body (JsonRpcMessageType0 | list[JsonRpcMessageType1Item]): One JSON-RPC 2.0 message, or a
            batch of them as a top-level array. A batch request is answered by a batch of responses.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ErrorResponse | JsonRpcMessageType0 | list[JsonRpcMessageType1Item]
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_request_id=x_request_id,
        )
    ).parsed
