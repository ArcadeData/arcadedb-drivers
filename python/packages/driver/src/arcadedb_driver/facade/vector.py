"""The `db.vector` namespace: kNN vector search, fused hybrid search, and full-text search.

Unlike `facade/timeseries.py` and `facade/dashboards.py`'s `GrafanaNamespace`, none of this
is hand-written. Those bypass the generated response models because the contract types their
per-element scalar values as `"type": "object"`, which makes the generated per-element model's
`from_dict` call `dict(value)` on an ordinary scalar and raise (or, worse, get silently
swallowed by `query`'s `oneOf` fallback). The vector endpoints' `results` items genuinely ARE
JSON objects - `VectorSearchResponseResultsItem`, `HybridSearchResponseResultsItem` and
`FullTextSearchResponseResultsItem` - so the same `dict(value)` call succeeds. This was checked
against a realistic payload before writing this module, not assumed from the shared "array of
object" shape in the contract.

Each method returns the whole generated response model, never unwrapped to `results`:
`VectorSearchResponse` and `HybridSearchResponse` carry `truncated`, and a caller reading only
the rows would silently work off a partial answer if that field were dropped (D-M5-2, the same
hazard `QueryEnvelope` documents for `query`/`command`). `FullTextSearchResponse` carries no
`truncated` at all - full-text search has no candidate-window concept to overflow - so that
asymmetry is left as-is rather than papered over with a uniform shape.

`k` (search, hybrid) and `limit` (fulltext) default to `UNSET` here, not to the contract's
documented default of 10: the server already applies that default when the field is omitted
from the JSON body, so re-asserting it client-side would just be a second, driftable copy of
the same number. This is also where `openapi-python-client` and `openapi-typescript` diverge on
a field that carries an OpenAPI `default` outside `required`: `openapi-typescript` (see
`typescript/CLAUDE.md`'s Task 1 notes) emits it as a REQUIRED property, forcing every caller to
pass a value the server would have defaulted anyway. `openapi-python-client` does not - it
types `k`/`limit` as `int | Unset` and gives the *generated request model's own* constructor
default of `10` rather than `UNSET`, so they are optional on `VectorSearchRequest` /
`HybridSearchRequest` / `FullTextSearchRequest` directly. No workaround was needed here; that
asymmetry between the two generators is worth recording precisely because Task 1 had to work
around it and this task did not.
"""

from __future__ import annotations

from .._generated.api.vector import full_text_search, hybrid_search, vector_search
from .._generated.client import Client
from .._generated.models.full_text_search_request import FullTextSearchRequest
from .._generated.models.full_text_search_response import FullTextSearchResponse
from .._generated.models.hybrid_search_request import HybridSearchRequest
from .._generated.models.hybrid_search_request_expand import HybridSearchRequestExpand
from .._generated.models.hybrid_search_request_weights import HybridSearchRequestWeights
from .._generated.models.hybrid_search_response import HybridSearchResponse
from .._generated.models.vector_search_request import VectorSearchRequest
from .._generated.models.vector_search_response import VectorSearchResponse
from .._generated.types import UNSET, Unset
from .._internal.unwrap import unwrap


class VectorNamespace:
    """kNN vector search, fused hybrid search, and full-text search - the `db.vector` namespace."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    def search(
        self,
        *,
        index_name: str,
        query_vector: list[float],
        k: int | Unset = UNSET,
        ef_search: int | Unset = UNSET,
        filter_: str | Unset = UNSET,
        query_indices: list[int] | Unset = UNSET,
        sparse: bool | Unset = UNSET,
    ) -> VectorSearchResponse:
        """kNN search over a dense (`LSM_VECTOR`) or sparse (`LSM_SPARSE_VECTOR`) index.

        Dense results carry `distance` (lower is better); sparse results carry `score`
        (higher is better) - `scoring` on the response names which. A filtered search
        inspects a bounded candidate window reported as `candidateLimit`, so `truncated`
        means the window was filled and more matches may exist - raise `k` to see them.
        """
        body = VectorSearchRequest(
            index_name=index_name,
            query_vector=query_vector,
            k=k,
            ef_search=ef_search,
            filter_=filter_,
            query_indices=query_indices,
            sparse=sparse,
        )
        data = unwrap(vector_search.sync_detailed(self._database, client=self._client, body=body))
        assert isinstance(data, VectorSearchResponse)
        return data

    def hybrid(
        self,
        *,
        vector_index_name: str,
        query_vector: list[float],
        k: int | Unset = UNSET,
        ef_search: int | Unset = UNSET,
        filter_: str | Unset = UNSET,
        query_indices: list[int] | Unset = UNSET,
        sparse: bool | Unset = UNSET,
        fulltext_index_name: str | Unset = UNSET,
        fulltext_query: str | Unset = UNSET,
        fusion_strategy: str | Unset = UNSET,
        expand: HybridSearchRequestExpand | Unset = UNSET,
        weights: HybridSearchRequestWeights | Unset = UNSET,
    ) -> HybridSearchResponse:
        """Fused vector, full-text and graph-expansion search.

        `fulltext_query` and `fulltext_index_name` go together: half a leg is refused by
        the server rather than silently dropped. `fused` on the response is `False` when
        only one leg produced rows - fusion needs at least two sources - in which case the
        response carries that leg's native distance or score instead of a fused one.
        """
        body = HybridSearchRequest(
            query_vector=query_vector,
            vector_index_name=vector_index_name,
            k=k,
            ef_search=ef_search,
            filter_=filter_,
            query_indices=query_indices,
            sparse=sparse,
            fulltext_index_name=fulltext_index_name,
            fulltext_query=fulltext_query,
            fusion_strategy=fusion_strategy,
            expand=expand,
            weights=weights,
        )
        data = unwrap(hybrid_search.sync_detailed(self._database, client=self._client, body=body))
        assert isinstance(data, HybridSearchResponse)
        return data

    def fulltext(
        self,
        *,
        query_text: str,
        index_name: str | Unset = UNSET,
        type_name: str | Unset = UNSET,
        limit: int | Unset = UNSET,
        properties: list[str] | Unset = UNSET,
    ) -> FullTextSearchResponse:
        """Full-text search over a `FULL_TEXT` index.

        `index_name` wins over `type_name` when both are given; `type_name` alone is only
        usable when that type carries exactly one full-text index. Unlike `search` and
        `hybrid`, the response carries no `truncated` - full-text search has no bounded
        candidate window to overflow, so there is nothing for that field to report.
        """
        body = FullTextSearchRequest(
            query_text=query_text,
            index_name=index_name,
            type_name=type_name,
            limit=limit,
            properties=properties,
        )
        data = unwrap(full_text_search.sync_detailed(self._database, client=self._client, body=body))
        assert isinstance(data, FullTextSearchResponse)
        return data


class AsyncVectorNamespace:
    """The async twin of `VectorNamespace`."""

    def __init__(self, client: Client, database: str) -> None:
        self._client = client
        self._database = database

    async def search(
        self,
        *,
        index_name: str,
        query_vector: list[float],
        k: int | Unset = UNSET,
        ef_search: int | Unset = UNSET,
        filter_: str | Unset = UNSET,
        query_indices: list[int] | Unset = UNSET,
        sparse: bool | Unset = UNSET,
    ) -> VectorSearchResponse:
        """kNN search over a dense (`LSM_VECTOR`) or sparse (`LSM_SPARSE_VECTOR`) index."""
        body = VectorSearchRequest(
            index_name=index_name,
            query_vector=query_vector,
            k=k,
            ef_search=ef_search,
            filter_=filter_,
            query_indices=query_indices,
            sparse=sparse,
        )
        data = unwrap(await vector_search.asyncio_detailed(self._database, client=self._client, body=body))
        assert isinstance(data, VectorSearchResponse)
        return data

    async def hybrid(
        self,
        *,
        vector_index_name: str,
        query_vector: list[float],
        k: int | Unset = UNSET,
        ef_search: int | Unset = UNSET,
        filter_: str | Unset = UNSET,
        query_indices: list[int] | Unset = UNSET,
        sparse: bool | Unset = UNSET,
        fulltext_index_name: str | Unset = UNSET,
        fulltext_query: str | Unset = UNSET,
        fusion_strategy: str | Unset = UNSET,
        expand: HybridSearchRequestExpand | Unset = UNSET,
        weights: HybridSearchRequestWeights | Unset = UNSET,
    ) -> HybridSearchResponse:
        """Fused vector, full-text and graph-expansion search."""
        body = HybridSearchRequest(
            query_vector=query_vector,
            vector_index_name=vector_index_name,
            k=k,
            ef_search=ef_search,
            filter_=filter_,
            query_indices=query_indices,
            sparse=sparse,
            fulltext_index_name=fulltext_index_name,
            fulltext_query=fulltext_query,
            fusion_strategy=fusion_strategy,
            expand=expand,
            weights=weights,
        )
        data = unwrap(await hybrid_search.asyncio_detailed(self._database, client=self._client, body=body))
        assert isinstance(data, HybridSearchResponse)
        return data

    async def fulltext(
        self,
        *,
        query_text: str,
        index_name: str | Unset = UNSET,
        type_name: str | Unset = UNSET,
        limit: int | Unset = UNSET,
        properties: list[str] | Unset = UNSET,
    ) -> FullTextSearchResponse:
        """Full-text search over a `FULL_TEXT` index."""
        body = FullTextSearchRequest(
            query_text=query_text,
            index_name=index_name,
            type_name=type_name,
            limit=limit,
            properties=properties,
        )
        data = unwrap(await full_text_search.asyncio_detailed(self._database, client=self._client, body=body))
        assert isinstance(data, FullTextSearchResponse)
        return data
