from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hybrid_search_response_results_item_properties import HybridSearchResponseResultsItemProperties


T = TypeVar("T", bound="HybridSearchResponseResultsItem")


@_attrs_define
class HybridSearchResponseResultsItem:
    """One fused hit

    Attributes:
        depth (int | Unset): Hops from the seed, for a hit the expansion leg contributed
        distance (float | Unset): Vector distance, present instead of 'fusedScore' on an unfused dense response
        fused_score (float | Unset): Fused score, higher is better. Present when 'fused' is true
        path (list[str] | Unset): Record ids from the seed to this hit, seed included
        properties (HybridSearchResponseResultsItemProperties | Unset): The record's properties
        rid (str | Unset): Record id of the hit
        score (float | Unset): Sparse or full-text score, present instead of 'fusedScore' on an unfused sparse or full-
            text response
        sources (list[str] | Unset): Which legs contributed this hit: vector, fulltext, expand
    """

    depth: int | Unset = UNSET
    distance: float | Unset = UNSET
    fused_score: float | Unset = UNSET
    path: list[str] | Unset = UNSET
    properties: HybridSearchResponseResultsItemProperties | Unset = UNSET
    rid: str | Unset = UNSET
    score: float | Unset = UNSET
    sources: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        depth = self.depth

        distance = self.distance

        fused_score = self.fused_score

        path: list[str] | Unset = UNSET
        if not isinstance(self.path, Unset):
            path = self.path

        properties: dict[str, Any] | Unset = UNSET
        if not isinstance(self.properties, Unset):
            properties = self.properties.to_dict()

        rid = self.rid

        score = self.score

        sources: list[str] | Unset = UNSET
        if not isinstance(self.sources, Unset):
            sources = self.sources

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if depth is not UNSET:
            field_dict["depth"] = depth
        if distance is not UNSET:
            field_dict["distance"] = distance
        if fused_score is not UNSET:
            field_dict["fusedScore"] = fused_score
        if path is not UNSET:
            field_dict["path"] = path
        if properties is not UNSET:
            field_dict["properties"] = properties
        if rid is not UNSET:
            field_dict["rid"] = rid
        if score is not UNSET:
            field_dict["score"] = score
        if sources is not UNSET:
            field_dict["sources"] = sources

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_response_results_item_properties import HybridSearchResponseResultsItemProperties

        d = dict(src_dict)
        depth = d.pop("depth", UNSET)

        distance = d.pop("distance", UNSET)

        fused_score = d.pop("fusedScore", UNSET)

        path = cast(list[str], d.pop("path", UNSET))

        _properties = d.pop("properties", UNSET)
        properties: HybridSearchResponseResultsItemProperties | Unset
        if isinstance(_properties, Unset):
            properties = UNSET
        else:
            properties = HybridSearchResponseResultsItemProperties.from_dict(_properties)

        rid = d.pop("rid", UNSET)

        score = d.pop("score", UNSET)

        sources = cast(list[str], d.pop("sources", UNSET))

        hybrid_search_response_results_item = cls(
            depth=depth,
            distance=distance,
            fused_score=fused_score,
            path=path,
            properties=properties,
            rid=rid,
            score=score,
            sources=sources,
        )

        hybrid_search_response_results_item.additional_properties = d
        return hybrid_search_response_results_item

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
