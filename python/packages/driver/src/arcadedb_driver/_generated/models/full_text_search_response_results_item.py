from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.full_text_search_response_results_item_properties import FullTextSearchResponseResultsItemProperties


T = TypeVar("T", bound="FullTextSearchResponseResultsItem")


@_attrs_define
class FullTextSearchResponseResultsItem:
    """One hit

    Attributes:
        distance (float | Unset): Dense vector distance, lower is better. Absent on a scored hit
        properties (FullTextSearchResponseResultsItemProperties | Unset): The record's properties
        rid (str | Unset): Record id of the hit
        score (float | Unset): Sparse or full-text score, higher is better. Absent on a distance hit
    """

    distance: float | Unset = UNSET
    properties: FullTextSearchResponseResultsItemProperties | Unset = UNSET
    rid: str | Unset = UNSET
    score: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        distance = self.distance

        properties: dict[str, Any] | Unset = UNSET
        if not isinstance(self.properties, Unset):
            properties = self.properties.to_dict()

        rid = self.rid

        score = self.score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if distance is not UNSET:
            field_dict["distance"] = distance
        if properties is not UNSET:
            field_dict["properties"] = properties
        if rid is not UNSET:
            field_dict["rid"] = rid
        if score is not UNSET:
            field_dict["score"] = score

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.full_text_search_response_results_item_properties import (
            FullTextSearchResponseResultsItemProperties,
        )

        d = dict(src_dict)
        distance = d.pop("distance", UNSET)

        _properties = d.pop("properties", UNSET)
        properties: FullTextSearchResponseResultsItemProperties | Unset
        if isinstance(_properties, Unset):
            properties = UNSET
        else:
            properties = FullTextSearchResponseResultsItemProperties.from_dict(_properties)

        rid = d.pop("rid", UNSET)

        score = d.pop("score", UNSET)

        full_text_search_response_results_item = cls(
            distance=distance,
            properties=properties,
            rid=rid,
            score=score,
        )

        full_text_search_response_results_item.additional_properties = d
        return full_text_search_response_results_item

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
