from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hybrid_search_request_expand import HybridSearchRequestExpand
    from ..models.hybrid_search_request_weights import HybridSearchRequestWeights


T = TypeVar("T", bound="HybridSearchRequest")


@_attrs_define
class HybridSearchRequest:
    """Fused vector, full-text and graph-expansion search

    Attributes:
        query_vector (list[float]): Query vector for the vector leg
        vector_index_name (str): Name of an LSM_VECTOR or LSM_SPARSE_VECTOR index
        ef_search (int | Unset): Dense-index search beam width
        expand (HybridSearchRequestExpand | Unset): Optional graph expansion leg, seeded from the union of the retrieval
            legs and ranked by breadth-first discovery order.
        filter_ (str | Unset): Optional read-only SQL WHERE predicate applied to the vector leg's candidate window
        fulltext_index_name (str | Unset): Full-text index the full-text leg searches. Required whenever 'fulltextQuery'
            is given, and refused without it
        fulltext_query (str | Unset): Lucene-syntax query for the full-text leg. Goes together with 'fulltextIndexName':
            half a leg is refused rather than silently dropped. Omit both to search without a full-text leg.
        fusion_strategy (str | Unset): How the legs are combined. Only RRF can consume the graph expansion leg, which is
            ranked by traversal order
        k (int | Unset): Maximum number of fused results to return Default: 10.
        query_indices (list[int] | Unset): Sparse dimension ids matching the 'queryVector' weights. Requires sparse=true
        sparse (bool | Unset): Use the sparse vector path
        weights (HybridSearchRequestWeights | Unset): Per-leg weight applied to every rank contribution. The only
            accepted keys are 'vector', 'fulltext' and 'expand', and a weight for a leg the request does not ask for is
            refused rather than ignored.
    """

    query_vector: list[float]
    vector_index_name: str
    ef_search: int | Unset = UNSET
    expand: HybridSearchRequestExpand | Unset = UNSET
    filter_: str | Unset = UNSET
    fulltext_index_name: str | Unset = UNSET
    fulltext_query: str | Unset = UNSET
    fusion_strategy: str | Unset = UNSET
    k: int | Unset = 10
    query_indices: list[int] | Unset = UNSET
    sparse: bool | Unset = UNSET
    weights: HybridSearchRequestWeights | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        query_vector = self.query_vector

        vector_index_name = self.vector_index_name

        ef_search = self.ef_search

        expand: dict[str, Any] | Unset = UNSET
        if not isinstance(self.expand, Unset):
            expand = self.expand.to_dict()

        filter_ = self.filter_

        fulltext_index_name = self.fulltext_index_name

        fulltext_query = self.fulltext_query

        fusion_strategy = self.fusion_strategy

        k = self.k

        query_indices: list[int] | Unset = UNSET
        if not isinstance(self.query_indices, Unset):
            query_indices = self.query_indices

        sparse = self.sparse

        weights: dict[str, Any] | Unset = UNSET
        if not isinstance(self.weights, Unset):
            weights = self.weights.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "queryVector": query_vector,
                "vectorIndexName": vector_index_name,
            }
        )
        if ef_search is not UNSET:
            field_dict["efSearch"] = ef_search
        if expand is not UNSET:
            field_dict["expand"] = expand
        if filter_ is not UNSET:
            field_dict["filter"] = filter_
        if fulltext_index_name is not UNSET:
            field_dict["fulltextIndexName"] = fulltext_index_name
        if fulltext_query is not UNSET:
            field_dict["fulltextQuery"] = fulltext_query
        if fusion_strategy is not UNSET:
            field_dict["fusionStrategy"] = fusion_strategy
        if k is not UNSET:
            field_dict["k"] = k
        if query_indices is not UNSET:
            field_dict["queryIndices"] = query_indices
        if sparse is not UNSET:
            field_dict["sparse"] = sparse
        if weights is not UNSET:
            field_dict["weights"] = weights

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_request_expand import HybridSearchRequestExpand
        from ..models.hybrid_search_request_weights import HybridSearchRequestWeights

        d = dict(src_dict)
        query_vector = cast(list[float], d.pop("queryVector"))

        vector_index_name = d.pop("vectorIndexName")

        ef_search = d.pop("efSearch", UNSET)

        _expand = d.pop("expand", UNSET)
        expand: HybridSearchRequestExpand | Unset
        if isinstance(_expand, Unset):
            expand = UNSET
        else:
            expand = HybridSearchRequestExpand.from_dict(_expand)

        filter_ = d.pop("filter", UNSET)

        fulltext_index_name = d.pop("fulltextIndexName", UNSET)

        fulltext_query = d.pop("fulltextQuery", UNSET)

        fusion_strategy = d.pop("fusionStrategy", UNSET)

        k = d.pop("k", UNSET)

        query_indices = cast(list[int], d.pop("queryIndices", UNSET))

        sparse = d.pop("sparse", UNSET)

        _weights = d.pop("weights", UNSET)
        weights: HybridSearchRequestWeights | Unset
        if isinstance(_weights, Unset):
            weights = UNSET
        else:
            weights = HybridSearchRequestWeights.from_dict(_weights)

        hybrid_search_request = cls(
            query_vector=query_vector,
            vector_index_name=vector_index_name,
            ef_search=ef_search,
            expand=expand,
            filter_=filter_,
            fulltext_index_name=fulltext_index_name,
            fulltext_query=fulltext_query,
            fusion_strategy=fusion_strategy,
            k=k,
            query_indices=query_indices,
            sparse=sparse,
            weights=weights,
        )

        hybrid_search_request.additional_properties = d
        return hybrid_search_request

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
