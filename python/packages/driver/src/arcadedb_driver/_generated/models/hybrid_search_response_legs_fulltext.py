from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="HybridSearchResponseLegsFulltext")


@_attrs_define
class HybridSearchResponseLegsFulltext:
    """The full-text leg, present whenever it ran - including when it matched nothing

    Attributes:
        count (int): Rows the full-text leg contributed to fusion
        index_name (str): Full-text index that was searched
        similarity (str): Similarity function that index scores with, e.g. BM25
    """

    count: int
    index_name: str
    similarity: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        count = self.count

        index_name = self.index_name

        similarity = self.similarity

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "count": count,
                "indexName": index_name,
                "similarity": similarity,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        count = d.pop("count")

        index_name = d.pop("indexName")

        similarity = d.pop("similarity")

        hybrid_search_response_legs_fulltext = cls(
            count=count,
            index_name=index_name,
            similarity=similarity,
        )

        hybrid_search_response_legs_fulltext.additional_properties = d
        return hybrid_search_response_legs_fulltext

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
