from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.full_text_search_response_similarity import FullTextSearchResponseSimilarity

if TYPE_CHECKING:
    from ..models.full_text_search_response_results_item import FullTextSearchResponseResultsItem


T = TypeVar("T", bound="FullTextSearchResponse")


@_attrs_define
class FullTextSearchResponse:
    """Documents matching the full-text query

    Attributes:
        count (int): Number of results returned
        index_name (str): Index that was searched
        results (list[FullTextSearchResponseResultsItem]): Hits, highest score first
        similarity (FullTextSearchResponseSimilarity): Similarity function the index scores with
    """

    count: int
    index_name: str
    results: list[FullTextSearchResponseResultsItem]
    similarity: FullTextSearchResponseSimilarity
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        index_name = self.index_name

        results = []
        for results_item_data in self.results:
            results_item = results_item_data.to_dict()
            results.append(results_item)

        similarity = self.similarity.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "indexName": index_name,
                "results": results,
                "similarity": similarity,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.full_text_search_response_results_item import FullTextSearchResponseResultsItem

        d = dict(src_dict)
        count = d.pop("count")

        index_name = d.pop("indexName")

        results = []
        _results = d.pop("results")
        for results_item_data in _results:
            results_item = FullTextSearchResponseResultsItem.from_dict(results_item_data)

            results.append(results_item)

        similarity = FullTextSearchResponseSimilarity(d.pop("similarity"))

        full_text_search_response = cls(
            count=count,
            index_name=index_name,
            results=results,
            similarity=similarity,
        )

        full_text_search_response.additional_properties = d
        return full_text_search_response

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
