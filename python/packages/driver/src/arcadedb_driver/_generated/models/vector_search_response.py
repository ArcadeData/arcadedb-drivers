from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.vector_search_response_results_item import VectorSearchResponseResultsItem


T = TypeVar("T", bound="VectorSearchResponse")


@_attrs_define
class VectorSearchResponse:
    """Ranked neighbors of the query vector

    Attributes:
        candidate_limit (int | Unset): Size of the candidate window the search inspected, which a filter over-fetches
            into
        count (int | Unset): Number of results returned
        index_name (str | Unset): Index that was searched
        results (list[VectorSearchResponseResultsItem] | Unset): Hits, nearest or highest-scoring first
        scoring (str | Unset): Which direction is better and how it was computed, e.g. 'distance_lower_is_better:COSINE'
            or 'score_higher_is_better:dot_product'. Read it rather than assuming, because the two paths rank in opposite
            directions.
        sparse (bool | Unset): Whether the sparse path was taken
        truncated (bool | Unset): True when the result window was filled, so further matches may exist. False for a
            short result: the search already returned every match it could find within 'candidateLimit'.
    """

    candidate_limit: int | Unset = UNSET
    count: int | Unset = UNSET
    index_name: str | Unset = UNSET
    results: list[VectorSearchResponseResultsItem] | Unset = UNSET
    scoring: str | Unset = UNSET
    sparse: bool | Unset = UNSET
    truncated: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        candidate_limit = self.candidate_limit

        count = self.count

        index_name = self.index_name

        results: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.results, Unset):
            results = []
            for results_item_data in self.results:
                results_item = results_item_data.to_dict()
                results.append(results_item)

        scoring = self.scoring

        sparse = self.sparse

        truncated = self.truncated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if candidate_limit is not UNSET:
            field_dict["candidateLimit"] = candidate_limit
        if count is not UNSET:
            field_dict["count"] = count
        if index_name is not UNSET:
            field_dict["indexName"] = index_name
        if results is not UNSET:
            field_dict["results"] = results
        if scoring is not UNSET:
            field_dict["scoring"] = scoring
        if sparse is not UNSET:
            field_dict["sparse"] = sparse
        if truncated is not UNSET:
            field_dict["truncated"] = truncated

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.vector_search_response_results_item import VectorSearchResponseResultsItem

        d = dict(src_dict)
        candidate_limit = d.pop("candidateLimit", UNSET)

        count = d.pop("count", UNSET)

        index_name = d.pop("indexName", UNSET)

        _results = d.pop("results", UNSET)
        results: list[VectorSearchResponseResultsItem] | Unset = UNSET
        if _results is not UNSET:
            results = []
            for results_item_data in _results:
                results_item = VectorSearchResponseResultsItem.from_dict(results_item_data)

                results.append(results_item)

        scoring = d.pop("scoring", UNSET)

        sparse = d.pop("sparse", UNSET)

        truncated = d.pop("truncated", UNSET)

        vector_search_response = cls(
            candidate_limit=candidate_limit,
            count=count,
            index_name=index_name,
            results=results,
            scoring=scoring,
            sparse=sparse,
            truncated=truncated,
        )

        vector_search_response.additional_properties = d
        return vector_search_response

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
