"""The `db.ts` namespace: ingesting and querying samples in a time-series type.

`write` is HAND-WRITTEN. `openapi-python-client` skips
`POST /api/v1/ts/{database}/write` because its body is `text/plain`, not JSON -
see `scripts/check_codegen_skips.py`, which pins that skip so a future contract
cannot silently drop another endpoint the same way. The request goes through the
generated client's own pooled httpx client, so it shares connections, headers and
timeout with every generated call.

`query` and `latest` are ALSO hand-written, for a related but distinct reason: the
contract types these responses' per-element scalar values (a timestamp, a numeric
measurement) as `"type": "object"` - see `TimeSeriesRawResponse.rows`,
`TimeSeriesAggregatedResponse.buckets[].values` and `TimeSeriesLatestResponse.latest`
in the contract. The generated per-element model's `from_dict` therefore calls
`dict(value)` on each element and raises `TypeError` on an ordinary scalar. For
`query` this is silent and worse than a crash: the generated `oneOf` parser in
`query_time_series.py` catches that `TypeError` and falls through to
`TimeSeriesAggregatedResponse`, whose fields are all optional so it "parses"
anything - every raw response comes back as a wrong-typed, empty-looking aggregated
object instead of raising. `latest` has no fallback branch, so it raises `TypeError`
outright on an ordinary response. `@arcadedb/driver` is unaffected only because
`openapi-fetch` performs no runtime validation, so the raw JSON passes straight
through unexamined; returning the parsed JSON body directly here is the equivalent -
and the only correct - behaviour until the contract is fixed upstream. Do not "fix"
this back to the generated models without fixing the contract first: it would
reintroduce the silent misclassification.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

import httpx

from .._generated.client import Client
from .._generated.types import UNSET, Unset
from ..errors import REQUEST_ID_HEADER, ArcadeDBError

#: Unit of the timestamps in a line-protocol payload. Defaults to nanoseconds server-side when omitted.
Precision = Literal["ns", "us", "ms", "s"]


def _write_url(database: str) -> str:
    return f"/api/v1/ts/{quote(database, safe='')}/write"


def _raise_for_status(raw: httpx.Response) -> None:
    """Raises `ArcadeDBError` unless the server answered 2xx."""
    if not 200 <= raw.status_code < 300:
        raise ArcadeDBError(raw.status_code, raw.content, raw.headers.get(REQUEST_ID_HEADER))


def _write_response(raw: httpx.Response) -> None:
    """Raises `ArcadeDBError` unless the server answered 2xx. The endpoint answers 204 with no body."""
    _raise_for_status(raw)


def _json_response(raw: httpx.Response) -> dict[str, Any]:
    """Raises `ArcadeDBError` unless the server answered 2xx; otherwise returns the parsed JSON
    body unaltered. Bypasses the generated response model - see the module docstring."""
    _raise_for_status(raw)
    body: dict[str, Any] = raw.json()
    return body


def _latest_params(*, type_: str, tag: str | Unset) -> dict[str, Any]:
    """Builds the query parameters for `GET .../latest` from `latest`'s own keyword
    parameters - mirroring the generated `get_time_series_latest._get_kwargs`, which this
    method cannot call directly (see the module docstring): `type_` (matching the generated
    operation's Python identifier, since `type` is a keyword) becomes the wire name `type`,
    and `tag` is dropped when left `UNSET`."""
    params: dict[str, Any] = {"type": type_, "tag": tag}
    return {key: value for key, value in params.items() if value is not UNSET and value is not None}


class TimeSeriesNamespace:
    """Ingests and queries samples in a time-series type - the `db.ts` namespace."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    def write(self, *, line_protocol: str, precision: Precision | None = None) -> None:
        """Ingests samples in InfluxDB Line Protocol.

        The endpoint takes the line-protocol text as a raw `text/plain` body, not
        JSON, which is why this is hand-written rather than generated.
        """
        raw = self._client.get_httpx_client().post(
            _write_url(self._database),
            content=line_protocol.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            params=None if precision is None else {"precision": precision},
        )
        _write_response(raw)

    def query(self, *, body: dict[str, Any]) -> dict[str, Any]:
        """Queries samples, optionally aggregated into buckets.

        Returns the parsed JSON body unaltered rather than a generated model - see
        the module docstring: the contract types this response's scalar column
        values as `"type": "object"`, which makes the generated model misparse
        (silently, for the raw shape) every realistic response.

        A name in `body["tags"]` that is not one of the type's declared TAG columns
        is refused server-side (400, naming the tag and the type's declared TAG
        columns) rather than dropped - see the README's "Time series" section.
        """
        raw = self._client.get_httpx_client().post(f"/api/v1/ts/{quote(self._database, safe='')}/query", json=body)
        return _json_response(raw)

    def latest(self, *, type_: str, tag: str | Unset = UNSET) -> dict[str, Any]:
        """Returns the most recent sample per series.

        `type_` and `tag` are exactly `get_time_series_latest`'s generated keyword
        parameters (`type_` because `type` is a Python keyword) - see the module
        docstring for why this bypasses the generated operation itself while still
        matching its signature, rather than accepting arbitrary `**kwargs` that the
        server would silently ignore if misspelled.

        Returns the parsed JSON body unaltered rather than the generated
        `TimeSeriesLatestResponse` - see the module docstring: the contract types
        `latest`'s scalar values as `"type": "object"`, so the generated model
        raises `TypeError` on an ordinary response.

        `tag` is refused server-side (400) when it is not in `name:value` form, or
        when its name is not one of the type's declared TAG columns - naming the
        tag and the type's declared TAG columns rather than skipping the filter.
        See the README's "Time series" section.
        """
        raw = self._client.get_httpx_client().get(
            f"/api/v1/ts/{quote(self._database, safe='')}/latest", params=_latest_params(type_=type_, tag=tag)
        )
        return _json_response(raw)


class AsyncTimeSeriesNamespace:
    """The async twin of `TimeSeriesNamespace`."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    async def write(self, *, line_protocol: str, precision: Precision | None = None) -> None:
        """Ingests samples in InfluxDB Line Protocol."""
        raw = await self._client.get_async_httpx_client().post(
            _write_url(self._database),
            content=line_protocol.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            params=None if precision is None else {"precision": precision},
        )
        _write_response(raw)

    async def query(self, *, body: dict[str, Any]) -> dict[str, Any]:
        """Queries samples, optionally aggregated into buckets."""
        raw = await self._client.get_async_httpx_client().post(
            f"/api/v1/ts/{quote(self._database, safe='')}/query", json=body
        )
        return _json_response(raw)

    async def latest(self, *, type_: str, tag: str | Unset = UNSET) -> dict[str, Any]:
        """Returns the most recent sample per series."""
        raw = await self._client.get_async_httpx_client().get(
            f"/api/v1/ts/{quote(self._database, safe='')}/latest", params=_latest_params(type_=type_, tag=tag)
        )
        return _json_response(raw)
