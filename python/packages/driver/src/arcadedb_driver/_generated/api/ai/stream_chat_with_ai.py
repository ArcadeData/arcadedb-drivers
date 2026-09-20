from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ai_chat_request import AiChatRequest
from ...models.ai_chat_stream_event import AiChatStreamEvent
from ...models.ai_protocol_error import AiProtocolError
from ...models.error_response import ErrorResponse
from ...types import Response


def _get_kwargs(
    *,
    body: AiChatRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/ai/chat/stream",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AiChatStreamEvent | AiProtocolError | ErrorResponse | None:
    if response.status_code == 200:
        response_200 = AiChatStreamEvent.from_dict(response.text)

        return response_200

    if response.status_code == 400:
        response_400 = AiProtocolError.from_dict(response.json())

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

    if response.status_code == 502:
        response_502 = ErrorResponse.from_dict(response.json())

        return response_502

    if response.status_code == 503:
        response_503 = ErrorResponse.from_dict(response.json())

        return response_503

    if response.status_code == 504:
        response_504 = ErrorResponse.from_dict(response.json())

        return response_504

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[AiChatStreamEvent | AiProtocolError | ErrorResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AiChatRequest,
) -> Response[AiChatStreamEvent | AiProtocolError | ErrorResponse]:
    """Send a message to the AI assistant, streaming the reply

     Sends one message in the context of a database, optionally continuing an existing chat by 'chatId',
    using a client-orchestrated streaming protocol so the AI gateway never has to open an inbound
    connection into the caller's network: the gateway emits 'tool_call' events on the response stream,
    the server executes each tool locally, and posts the result back to the gateway to resume the loop.
    The 200 response is always 'text/event-stream', never a JSON body; the closing 'done' event carries
    the same 'response', 'commands', and 'chatId' fields as POST /api/v1/ai/chat's JSON response. For a
    single non-streaming JSON reply instead, use POST /api/v1/ai/chat.

    The gateway's own 'session' and 'tool_call' events are NOT forwarded: this server consumes both -
    the first to learn where to post tool results, the second to run the tool - and emits a
    'tool_start'/'tool_end' pair around each run in their place. See AiChatStreamEvent.

    The assistant is a remote dependency: 503 means the gateway was unreachable and 504 that it did not
    answer in time. Both are retryable. A rejected subscription token answers 502, remapped from the
    gateway's own 401 or 403 so it cannot be mistaken for this request's own authentication failing.

    Args:
        body (AiChatRequest): Chat message

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AiChatStreamEvent | AiProtocolError | ErrorResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: AiChatRequest,
) -> AiChatStreamEvent | AiProtocolError | ErrorResponse | None:
    """Send a message to the AI assistant, streaming the reply

     Sends one message in the context of a database, optionally continuing an existing chat by 'chatId',
    using a client-orchestrated streaming protocol so the AI gateway never has to open an inbound
    connection into the caller's network: the gateway emits 'tool_call' events on the response stream,
    the server executes each tool locally, and posts the result back to the gateway to resume the loop.
    The 200 response is always 'text/event-stream', never a JSON body; the closing 'done' event carries
    the same 'response', 'commands', and 'chatId' fields as POST /api/v1/ai/chat's JSON response. For a
    single non-streaming JSON reply instead, use POST /api/v1/ai/chat.

    The gateway's own 'session' and 'tool_call' events are NOT forwarded: this server consumes both -
    the first to learn where to post tool results, the second to run the tool - and emits a
    'tool_start'/'tool_end' pair around each run in their place. See AiChatStreamEvent.

    The assistant is a remote dependency: 503 means the gateway was unreachable and 504 that it did not
    answer in time. Both are retryable. A rejected subscription token answers 502, remapped from the
    gateway's own 401 or 403 so it cannot be mistaken for this request's own authentication failing.

    Args:
        body (AiChatRequest): Chat message

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AiChatStreamEvent | AiProtocolError | ErrorResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: AiChatRequest,
) -> Response[AiChatStreamEvent | AiProtocolError | ErrorResponse]:
    """Send a message to the AI assistant, streaming the reply

     Sends one message in the context of a database, optionally continuing an existing chat by 'chatId',
    using a client-orchestrated streaming protocol so the AI gateway never has to open an inbound
    connection into the caller's network: the gateway emits 'tool_call' events on the response stream,
    the server executes each tool locally, and posts the result back to the gateway to resume the loop.
    The 200 response is always 'text/event-stream', never a JSON body; the closing 'done' event carries
    the same 'response', 'commands', and 'chatId' fields as POST /api/v1/ai/chat's JSON response. For a
    single non-streaming JSON reply instead, use POST /api/v1/ai/chat.

    The gateway's own 'session' and 'tool_call' events are NOT forwarded: this server consumes both -
    the first to learn where to post tool results, the second to run the tool - and emits a
    'tool_start'/'tool_end' pair around each run in their place. See AiChatStreamEvent.

    The assistant is a remote dependency: 503 means the gateway was unreachable and 504 that it did not
    answer in time. Both are retryable. A rejected subscription token answers 502, remapped from the
    gateway's own 401 or 403 so it cannot be mistaken for this request's own authentication failing.

    Args:
        body (AiChatRequest): Chat message

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AiChatStreamEvent | AiProtocolError | ErrorResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: AiChatRequest,
) -> AiChatStreamEvent | AiProtocolError | ErrorResponse | None:
    """Send a message to the AI assistant, streaming the reply

     Sends one message in the context of a database, optionally continuing an existing chat by 'chatId',
    using a client-orchestrated streaming protocol so the AI gateway never has to open an inbound
    connection into the caller's network: the gateway emits 'tool_call' events on the response stream,
    the server executes each tool locally, and posts the result back to the gateway to resume the loop.
    The 200 response is always 'text/event-stream', never a JSON body; the closing 'done' event carries
    the same 'response', 'commands', and 'chatId' fields as POST /api/v1/ai/chat's JSON response. For a
    single non-streaming JSON reply instead, use POST /api/v1/ai/chat.

    The gateway's own 'session' and 'tool_call' events are NOT forwarded: this server consumes both -
    the first to learn where to post tool results, the second to run the tool - and emits a
    'tool_start'/'tool_end' pair around each run in their place. See AiChatStreamEvent.

    The assistant is a remote dependency: 503 means the gateway was unreachable and 504 that it did not
    answer in time. Both are retryable. A rejected subscription token answers 502, remapped from the
    gateway's own 401 or 403 so it cannot be mistaken for this request's own authentication failing.

    Args:
        body (AiChatRequest): Chat message

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AiChatStreamEvent | AiProtocolError | ErrorResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
