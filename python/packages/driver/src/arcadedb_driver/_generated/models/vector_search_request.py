from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VectorSearchRequest")


@_attrs_define
class VectorSearchRequest:
    """kNN search over a dense or sparse vector index

    Attributes:
        index_name (str): Name of an LSM_VECTOR or LSM_SPARSE_VECTOR index
        query_vector (list[float]): Dense query vector, or the sparse weights matching 'queryIndices' when sparse is
            true
        ef_search (int | Unset): Dense-index search beam width: higher values improve recall at higher cost. Rejected
            for a sparse index
        filter_ (str | Unset): Optional read-only SQL WHERE predicate applied to a bounded candidate set. Evaluated
            against each expanded neighbor row, where record properties are flattened and @rid, @type, record, plus distance
            (dense) or score (sparse) are available. At most4096 characters.
        k (int | Unset): Maximum number of results to return Default: 10.
        query_indices (list[int] | Unset): Sparse dimension ids matching the 'queryVector' weights; omit to use the
            vector's own positions. Requires sparse=true
        sparse (bool | Unset): Search an LSM_SPARSE_VECTOR index instead of a dense one
    """

    index_name: str
    query_vector: list[float]
    ef_search: int | Unset = UNSET
    filter_: str | Unset = UNSET
    k: int | Unset = 10
    query_indices: list[int] | Unset = UNSET
    sparse: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        index_name = self.index_name

        query_vector = self.query_vector

        ef_search = self.ef_search

        filter_ = self.filter_

        k = self.k

        query_indices: list[int] | Unset = UNSET
        if not isinstance(self.query_indices, Unset):
            query_indices = self.query_indices

        sparse = self.sparse

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "indexName": index_name,
                "queryVector": query_vector,
            }
        )
        if ef_search is not UNSET:
            field_dict["efSearch"] = ef_search
        if filter_ is not UNSET:
            field_dict["filter"] = filter_
        if k is not UNSET:
            field_dict["k"] = k
        if query_indices is not UNSET:
            field_dict["queryIndices"] = query_indices
        if sparse is not UNSET:
            field_dict["sparse"] = sparse

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        index_name = d.pop("indexName")

        query_vector = cast(list[float], d.pop("queryVector"))

        ef_search = d.pop("efSearch", UNSET)

        filter_ = d.pop("filter", UNSET)

        k = d.pop("k", UNSET)

        query_indices = cast(list[int], d.pop("queryIndices", UNSET))

        sparse = d.pop("sparse", UNSET)

        vector_search_request = cls(
            index_name=index_name,
            query_vector=query_vector,
            ef_search=ef_search,
            filter_=filter_,
            k=k,
            query_indices=query_indices,
            sparse=sparse,
        )

        vector_search_request.additional_properties = d
        return vector_search_request

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
