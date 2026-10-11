"""The `db.grafana` and `db.promql` namespaces.

`db.promql` passes the generated request and response models through unaltered,
exactly as `facade/dashboards.ts` re-exports `components["schemas"][...]` unaltered.
`Unset` is visible on optional fields here in the same way `?: T | undefined` is
visible in TypeScript; the normalising `QueryEnvelope` treatment is deliberately
confined to the data plane.

`db.grafana.query` is HAND-WRITTEN, unlike `db.promql` - the same family of defect
as `db.ts.query`/`db.ts.latest` (see `facade/timeseries.py`'s module docstring for
the full explanation): the contract types `GrafanaQueryResponse`'s per-element
scalar DataFrame values as `"type": "object"`, so the generated per-element model's
`from_dict` calls `dict(value)` on each element and raises `TypeError` on an
ordinary scalar. `query` therefore bypasses the generated response parsing and
returns the parsed JSON body directly, through the generated client's own pooled
httpx client so auth headers, timeout and connection pooling still apply. Do not
"fix" this back to the generated model without fixing the contract first.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .._generated.api.prom_ql import (
    prom_ql_labels,
    prom_ql_query,
    prom_ql_query_range,
    prom_ql_series,
)
from .._generated.client import Client
from .._generated.models.prom_ql_data_response import PromQLDataResponse
from .._generated.models.prom_ql_labels_response import PromQLLabelsResponse
from .._generated.models.prom_ql_series_response import PromQLSeriesResponse
from .._generated.types import UNSET, Unset
from .._internal.unwrap import unwrap
from ..errors import ArcadeDBError


def _json_response(raw: httpx.Response) -> dict[str, Any]:
    """Raises `ArcadeDBError` unless the server answered 2xx; otherwise returns the parsed JSON
    body unaltered. Bypasses the generated response model - see the module docstring."""
    if not 200 <= raw.status_code < 300:
        raise ArcadeDBError.from_httpx_response(raw)
    body: dict[str, Any] = raw.json()
    return body


class GrafanaNamespace:
    """Grafana panel queries over a time-series type - the `db.grafana` namespace."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    def query(self, *, body: dict[str, Any]) -> dict[str, Any]:
        """Executes one query per `targets` entry, returning DataFrames keyed by `refId`.

        Returns the parsed JSON body unaltered rather than the generated
        `GrafanaQueryResponse` - see the module docstring.
        """
        raw = self._client.get_httpx_client().post(
            f"/api/v1/ts/{quote(self._database, safe='')}/grafana/query", json=body
        )
        return _json_response(raw)


class PromQLNamespace:
    """A Prometheus-compatible query surface over a time-series type - the `db.promql` namespace."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    def query(
        self, *, query: str, time: str | Unset = UNSET, lookback_delta: str | Unset = UNSET
    ) -> PromQLDataResponse:
        """Evaluates a PromQL expression at one instant."""
        data = unwrap(
            prom_ql_query.sync_detailed(
                self._database, client=self._client, query=query, time=time, lookback_delta=lookback_delta
            )
        )
        assert isinstance(data, PromQLDataResponse)
        return data

    def query_range(
        self, *, query: str, start: str, end: str, step: str, lookback_delta: str | Unset = UNSET
    ) -> PromQLDataResponse:
        """Evaluates a PromQL expression at every step across a range."""
        data = unwrap(
            prom_ql_query_range.sync_detailed(
                self._database,
                client=self._client,
                query=query,
                start=start,
                end=end,
                step=step,
                lookback_delta=lookback_delta,
            )
        )
        assert isinstance(data, PromQLDataResponse)
        return data

    def labels(self) -> PromQLLabelsResponse:
        """Lists every label name present in the database, sorted, always including `__name__`."""
        data = unwrap(prom_ql_labels.sync_detailed(self._database, client=self._client))
        assert isinstance(data, PromQLLabelsResponse)
        return data

    def series(self, *, match: list[str], start: str | Unset = UNSET, end: str | Unset = UNSET) -> PromQLSeriesResponse:
        """Returns the label sets of the series matching the given `match[]` selectors."""
        data = unwrap(
            prom_ql_series.sync_detailed(self._database, client=self._client, match=match, start=start, end=end)
        )
        assert isinstance(data, PromQLSeriesResponse)
        return data


class AsyncGrafanaNamespace:
    """The async twin of `GrafanaNamespace`."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    async def query(self, *, body: dict[str, Any]) -> dict[str, Any]:
        """Executes one query per `targets` entry, returning DataFrames keyed by `refId`."""
        raw = await self._client.get_async_httpx_client().post(
            f"/api/v1/ts/{quote(self._database, safe='')}/grafana/query", json=body
        )
        return _json_response(raw)


class AsyncPromQLNamespace:
    """The async twin of `PromQLNamespace`."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    async def query(
        self, *, query: str, time: str | Unset = UNSET, lookback_delta: str | Unset = UNSET
    ) -> PromQLDataResponse:
        """Evaluates a PromQL expression at one instant."""
        data = unwrap(
            await prom_ql_query.asyncio_detailed(
                self._database, client=self._client, query=query, time=time, lookback_delta=lookback_delta
            )
        )
        assert isinstance(data, PromQLDataResponse)
        return data

    async def query_range(
        self, *, query: str, start: str, end: str, step: str, lookback_delta: str | Unset = UNSET
    ) -> PromQLDataResponse:
        """Evaluates a PromQL expression at every step across a range."""
        data = unwrap(
            await prom_ql_query_range.asyncio_detailed(
                self._database,
                client=self._client,
                query=query,
                start=start,
                end=end,
                step=step,
                lookback_delta=lookback_delta,
            )
        )
        assert isinstance(data, PromQLDataResponse)
        return data

    async def labels(self) -> PromQLLabelsResponse:
        """Lists every label name present in the database, sorted, always including `__name__`."""
        data = unwrap(await prom_ql_labels.asyncio_detailed(self._database, client=self._client))
        assert isinstance(data, PromQLLabelsResponse)
        return data

    async def series(
        self, *, match: list[str], start: str | Unset = UNSET, end: str | Unset = UNSET
    ) -> PromQLSeriesResponse:
        """Returns the label sets of the series matching the given `match[]` selectors."""
        data = unwrap(
            await prom_ql_series.asyncio_detailed(
                self._database, client=self._client, match=match, start=start, end=end
            )
        )
        assert isinstance(data, PromQLSeriesResponse)
        return data
