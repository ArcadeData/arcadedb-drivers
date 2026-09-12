"""Splitting an ndjson byte stream into lines, for every endpoint that streams one.

Split on `"\\n"` and nothing else. `httpx`'s own `iter_lines()` cannot be used: it splits on
`str.splitlines()` semantics, which treats U+0085, U+2028 and U+2029 as line terminators. JSON
permits all three raw inside a string, so a single record containing one is torn into two
fragments, neither of which parses. Verified on httpx 0.28.1.

Lives here rather than in `facade/stream.py` because two endpoints stream ndjson - query/command
and batch - and the splitting is identical for both. `raise_for_status`/`araise_for_status` live
here too, for the same reason: both streaming endpoints need the same "read the body before
raising" handling, and a module per function would be worse than one module shared by both.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx

from ..errors import REQUEST_ID_HEADER, ArcadeDBError


def raise_for_status(response: httpx.Response) -> None:
    """Raises `ArcadeDBError` unless the server answered 2xx.

    Reads the body first: a streaming response has not been read yet, and `ArcadeDBError` needs
    the body for the server's detail.
    """
    if not response.is_success:
        response.read()
        raise ArcadeDBError(response.status_code, response.content, response.headers.get(REQUEST_ID_HEADER))


async def araise_for_status(response: httpx.Response) -> None:
    """The async twin of `raise_for_status`."""
    if not response.is_success:
        await response.aread()
        raise ArcadeDBError(response.status_code, response.content, response.headers.get(REQUEST_ID_HEADER))


def iter_ndjson_lines(chunks: Iterator[str]) -> Iterator[str]:
    """Splits already-decoded text chunks into ndjson lines on `"\\n"` and nothing else.

    See the module docstring for why `iter_lines()` cannot be used for this. A `remainder` carries
    whatever the last chunk left unterminated into the next one, and is emitted after the stream
    ends so a final line with no trailing newline is not dropped.
    """
    remainder = ""
    for chunk in chunks:
        remainder += chunk
        *lines, remainder = remainder.split("\n")
        yield from lines
    if remainder:
        yield remainder


async def aiter_ndjson_lines(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    """The async twin of `iter_ndjson_lines`."""
    remainder = ""
    async for chunk in chunks:
        remainder += chunk
        *lines, remainder = remainder.split("\n")
        for line in lines:
            yield line
    if remainder:
        yield remainder
