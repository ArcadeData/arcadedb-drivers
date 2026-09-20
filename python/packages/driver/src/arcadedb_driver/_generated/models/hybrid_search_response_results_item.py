from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.hybrid_search_response_results_item_sources_item import HybridSearchResponseResultsItemSourcesItem
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hybrid_search_response_results_item_properties import HybridSearchResponseResultsItemProperties


T = TypeVar("T", bound="HybridSearchResponseResultsItem")


@_attrs_define
class HybridSearchResponseResultsItem:
    """One fused hit

    Attributes:
        properties (HybridSearchResponseResultsItemProperties): The record's properties. An open map: besides the type's
            own properties it carries the record's '@rid' and '@type', which JsonSerializer writes into every serialized
            document.
        rid (str): Record id of the hit
        sources (list[HybridSearchResponseResultsItemSourcesItem]): Which legs contributed this hit. Never empty: a hit
            is in the list because some leg produced it
        depth (int | Unset): Hops from the seed, for a hit the expansion leg contributed
        distance (float | Unset): Vector distance, present instead of 'fusedScore' on an unfused dense response
        fused_score (float | Unset): Fused score, higher is better. Present when 'fused' is true
        path (list[str] | Unset): Record ids from the seed to this hit, seed included
        score (float | Unset): Sparse or full-text score, present instead of 'fusedScore' on an unfused sparse or full-
            text response
    """

    properties: HybridSearchResponseResultsItemProperties
    rid: str
    sources: list[HybridSearchResponseResultsItemSourcesItem]
    depth: int | Unset = UNSET
    distance: float | Unset = UNSET
    fused_score: float | Unset = UNSET
    path: list[str] | Unset = UNSET
    score: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        properties = self.properties.to_dict()

        rid = self.rid

        sources = []
        for sources_item_data in self.sources:
            sources_item = sources_item_data.value
            sources.append(sources_item)

        depth = self.depth

        distance = self.distance

        fused_score = self.fused_score

        path: list[str] | Unset = UNSET
        if not isinstance(self.path, Unset):
            path = self.path

        score = self.score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "properties": properties,
                "rid": rid,
                "sources": sources,
            }
        )
        if depth is not UNSET:
            field_dict["depth"] = depth
        if distance is not UNSET:
            field_dict["distance"] = distance
        if fused_score is not UNSET:
            field_dict["fusedScore"] = fused_score
        if path is not UNSET:
            field_dict["path"] = path
        if score is not UNSET:
            field_dict["score"] = score

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hybrid_search_response_results_item_properties import HybridSearchResponseResultsItemProperties

        d = dict(src_dict)
        properties = HybridSearchResponseResultsItemProperties.from_dict(d.pop("properties"))

        rid = d.pop("rid")

        sources = []
        _sources = d.pop("sources")
        for sources_item_data in _sources:
            sources_item = HybridSearchResponseResultsItemSourcesItem(sources_item_data)

            sources.append(sources_item)

        depth = d.pop("depth", UNSET)

        distance = d.pop("distance", UNSET)

        fused_score = d.pop("fusedScore", UNSET)

        path = cast(list[str], d.pop("path", UNSET))

        score = d.pop("score", UNSET)

        hybrid_search_response_results_item = cls(
            properties=properties,
            rid=rid,
            sources=sources,
            depth=depth,
            distance=distance,
            fused_score=fused_score,
            path=path,
            score=score,
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
